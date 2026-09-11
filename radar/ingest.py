"""Ingesta: llena la base de datos desde samples locales, seed o las fuentes.

Modos:
  --from-samples  (por defecto) lee ficheros locales, no toca la red.
  --seed          carga seed/seed.jsonl (formato canónico).
  --live          descubrimiento RSS + metadatos oEmbed (gratis) + transcripciones
                  Thordata (1 crédito por vídeo). `--dry-run` enseña el gasto y
                  sale sin gastar.

Reglas de coste: deduplicación por video_id, límite duro de transcripciones por
ejecución, confirmación antes de gastar y resumen final de créditos y tiempo.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import db
from .config import ROOT, Settings, get_settings
from .index import IndexSummary, build_chunks
from .models import TranscriptDoc, VideoMeta
from .parsers import (
    ParserPendingError,
    channel_from_record,
    subtitle_filename_parts,
    subtitle_segments,
    transcript_from_record,
    transcript_tasks_from_raw,
    video_from_record,
)
from .sources import (
    SourceError,
    discovery_source,
    metadata_source,
    transcript_source,
)
from .thordata import CreditsExhausted, TaskTimeout, ThordataClient, ThordataError

SUBTITLE_SUFFIXES = {".txt", ".vtt", ".srt"}
_CHANNEL_ID_RE = re.compile(r"UC[\w-]{22}")
_HANDLE_IN_URL_RE = re.compile(r"youtube\.com/(@[\w.-]+)")


@dataclass
class Summary:
    channels: int = 0
    new_videos: int = 0
    new_transcripts: int = 0
    segments: int = 0
    chunks: int = 0
    thordata_calls: int = 0
    credits: int = 0
    skipped: int = 0
    errors: int = 0
    languages: dict[str, int] = field(default_factory=dict)
    seconds: float = 0.0
    notes: list[str] = field(default_factory=list)

    def render(self) -> str:
        langs = ", ".join(f"{k}={v}" for k, v in sorted(self.languages.items())) or "-"
        minutes, seconds = divmod(int(self.seconds), 60)
        lines = [
            "Resumen de ingesta:",
            f"  canales:               {self.channels}",
            f"  vídeos nuevos:         {self.new_videos}",
            f"  transcripciones:       {self.new_transcripts}",
            f"  idiomas:               {langs}",
            f"  segmentos:             {self.segments}",
            f"  chunks:                {self.chunks}",
            f"  peticiones Thordata:   {self.thordata_calls}",
            f"  créditos gastados:     {self.credits}",
            f"  errores:               {self.errors}",
            f"  tiempo total:          {minutes}m {seconds}s",
        ]
        lines += [f"  nota: {n}" for n in self.notes]
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Configuración de fuentes
# --------------------------------------------------------------------------- #


def load_sources(path: Path | str = ROOT / "config" / "sources.yaml") -> dict:
    path = Path(path)
    if not path.exists():
        return {"channels": [], "languages_fallback": ["en-orig", "en"], "window_days": 7}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _entry_from_string(value: str) -> dict:
    value = value.strip()
    if _CHANNEL_ID_RE.fullmatch(value):
        return {"channel_id": value}
    if value.startswith("@"):
        return {"handle": value}
    if "youtube.com" in value:
        match = _HANDLE_IN_URL_RE.search(value)
        return {"url": value, "handle": match.group(1) if match else ""}
    return {"handle": value}


def normalize_channels(sources: dict) -> list[dict]:
    normalized = []
    for entry in sources.get("channels", []) or []:
        if isinstance(entry, str):
            entry = _entry_from_string(entry)
        normalized.append(
            {
                "channel_id": str(entry.get("channel_id", "") or ""),
                "handle": str(entry.get("handle", "") or ""),
                "url": str(entry.get("url", "") or ""),
                "name": str(entry.get("name", "") or ""),
                "lang": str(entry.get("lang", "") or ""),
                "playlist_id": str(entry.get("playlist_id", "") or ""),
                "user": str(entry.get("user", "") or ""),
                "max_posts": int(entry.get("max_posts", 15) or 15),
            }
        )
    return normalized


# --------------------------------------------------------------------------- #
# Modo samples (offline)
# --------------------------------------------------------------------------- #


def ingest_from_samples(conn, samples_dir: Path, summary: Summary) -> Summary:
    samples_dir = Path(samples_dir)
    files = sorted(
        path
        for path in samples_dir.rglob("*")
        if path.is_file() and path.name != ".gitkeep"
    )
    if not files:
        summary.notes.append(
            f"No hay ficheros en {samples_dir}. Deja ahí los samples del panel."
        )
        return summary
    for path in files:
        try:
            if path.suffix.lower() in SUBTITLE_SUFFIXES:
                _ingest_subtitle_sample(conn, path, summary)
            elif path.suffix.lower() == ".json":
                _ingest_json_sample(conn, path, summary)
            else:
                summary.notes.append(f"{path.name}: tipo no reconocido, omitido")
        except ParserPendingError as exc:
            summary.notes.append(f"{path.name}: {exc}")
        except (json.JSONDecodeError, OSError) as exc:
            summary.notes.append(f"{path.name}: {exc}")
    return summary


def _ingest_json_sample(conn, path: Path, summary: Summary) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if _looks_like_transcript_result(raw):
        for task in transcript_tasks_from_raw(raw):
            subtitle = _find_subtitle_file(path.parent, task.video_id)
            if subtitle:
                _ingest_subtitle_sample(conn, subtitle, summary)
            else:
                summary.notes.append(
                    f"{path.name}: {task.video_id} apunta a un .vtt que no está en "
                    f"{path.parent.name}/"
                )
        return
    _store_video(conn, video_from_record(raw), summary)


def _ingest_subtitle_sample(conn, path: Path, summary: Summary) -> None:
    parts = subtitle_filename_parts(path.name)
    if not parts:
        summary.notes.append(f"{path.name}: no pude deducir video_id/idioma del nombre")
        return
    video_id, lang = parts
    if not db.video_exists(conn, video_id):
        db.upsert_video(conn, VideoMeta(video_id=video_id, lang=lang), None)
    segments = subtitle_segments(
        path.read_text(encoding="utf-8", errors="replace"), video_id, lang
    )
    doc = TranscriptDoc(
        video_id=video_id, lang=lang, subtitle_type="auto_generated", segments=segments
    )
    _store_transcript(conn, doc, path, summary)


def _find_subtitle_file(directory: Path, video_id: str) -> Path | None:
    for candidate in sorted(directory.glob(f"{video_id}_*")):
        if candidate.suffix.lower() in SUBTITLE_SUFFIXES:
            return candidate
    return None


def _looks_like_transcript_result(raw) -> bool:
    records = raw
    if isinstance(raw, dict):
        for key in ("data", "result", "results"):
            if isinstance(raw.get(key), list):
                records = raw[key]
                break
    return isinstance(records, list) and any(
        isinstance(record, dict) and record.get("transcriptDownloadUrl")
        for record in records
    )


def _store_video(conn, meta: VideoMeta, summary: Summary) -> None:
    if db.video_exists(conn, meta.video_id):
        summary.skipped += 1
    else:
        summary.new_videos += 1
    db.upsert_video(conn, meta, db.channel_id_for(conn, meta.channel_handle))


def _store_transcript(conn, doc: TranscriptDoc, raw_path: Path | None, summary: Summary) -> None:
    if db.has_transcript(conn, doc.video_id, doc.lang, doc.subtitle_type):
        summary.skipped += 1
        return
    db.save_transcript(
        conn,
        doc.video_id,
        doc.lang,
        doc.subtitle_type,
        doc.segments,
        raw_path=str(raw_path or ""),
    )
    summary.new_transcripts += 1
    summary.segments += len(doc.segments)
    summary.languages[doc.lang] = summary.languages.get(doc.lang, 0) + 1


# --------------------------------------------------------------------------- #
# Modo seed (canónico)
# --------------------------------------------------------------------------- #


def ingest_seed(conn, seed_path: Path, summary: Summary) -> Summary:
    seed_path = Path(seed_path)
    if not seed_path.exists():
        summary.notes.append(f"No existe {seed_path}.")
        return summary
    for line in seed_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        kind = obj.get("type")
        if kind == "channel":
            ch = channel_from_record(obj)
            db.upsert_channel(conn, ch.handle, ch.url, ch.name, ch.lang, ch.channel_id)
        elif kind == "video":
            meta = video_from_record(obj)
            if not db.video_exists(conn, meta.video_id):
                summary.new_videos += 1
            db.upsert_video(conn, meta, db.channel_id_for(conn, meta.channel_handle))
        elif kind == "transcript":
            doc = transcript_from_record(obj)
            if db.has_transcript(conn, doc.video_id, doc.lang, doc.subtitle_type):
                summary.skipped += 1
            else:
                db.save_transcript(
                    conn, doc.video_id, doc.lang, doc.subtitle_type, doc.segments
                )
                summary.new_transcripts += 1
                summary.segments += len(doc.segments)
                summary.languages[doc.lang] = summary.languages.get(doc.lang, 0) + 1
        else:
            summary.notes.append(f"seed: tipo desconocido {kind!r}")
    conn.commit()
    return summary


# --------------------------------------------------------------------------- #
# Modo live: RSS (descubrimiento) + oEmbed (metadatos) + Thordata (transcripción)
# --------------------------------------------------------------------------- #


@dataclass
class ChannelPlan:
    channel: dict
    refs: list = field(default_factory=list)
    error: str = ""


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _resolve_channel(conn, channel: dict, discovery) -> str:
    if channel.get("channel_id"):
        return channel["channel_id"]
    handle = channel.get("handle", "")
    if handle:
        row = db.channel_row(conn, handle)
        if row and row["channel_id"]:
            return row["channel_id"]
    target = channel.get("url") or handle
    if not target:
        raise SourceError("canal sin channel_id, handle ni url")
    channel_id = discovery.resolve_channel_id(target)
    if handle:
        db.upsert_channel(
            conn,
            handle,
            channel.get("url", ""),
            channel.get("name", ""),
            channel.get("lang", ""),
            channel_id,
        )
        conn.commit()
    return channel_id


def build_plan(conn, channels: list[dict], discovery, days: int) -> list[ChannelPlan]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    plans: list[ChannelPlan] = []
    for channel in channels:
        try:
            channel_id = _resolve_channel(conn, channel, discovery)
        except Exception as exc:  # noqa: BLE001 - se reporta y se sigue
            plans.append(ChannelPlan(channel=channel, error=str(exc)))
            continue
        channel = {**channel, "channel_id": channel_id}
        try:
            refs = discovery.discover(channel)
        except Exception as exc:  # noqa: BLE001
            plans.append(ChannelPlan(channel=channel, error=str(exc)))
            continue
        recent = [
            ref
            for ref in refs
            if (_parse_dt(ref.published_at) or datetime.min.replace(tzinfo=timezone.utc))
            >= cutoff
        ]
        plans.append(ChannelPlan(channel=channel, refs=recent))
    return plans


def _print_plan(plans: list[ChannelPlan]) -> None:
    for plan in plans:
        label = plan.channel.get("handle") or plan.channel.get("channel_id") or "?"
        if plan.error:
            print(f"  {label:34} ERROR  {plan.error}")
        else:
            print(
                f"  {label:34} {len(plan.refs):3} vídeos en ventana  "
                f"(lang={plan.channel.get('lang') or '?'})"
            )


def ingest_live(conn, settings: Settings, sources: dict, summary: Summary, args) -> Summary:
    start = time.monotonic()
    discovery = discovery_source(settings)
    metadata = metadata_source(settings)
    channels = normalize_channels(sources)
    summary.channels = len(channels)
    days = args.days or int(sources.get("window_days", 7) or 7)

    plans = build_plan(conn, channels, discovery, days)
    print(f"Plan de descubrimiento (últimos {days} días):")
    _print_plan(plans)

    targets = [
        (plan, ref)
        for plan in plans
        for ref in plan.refs
        if not db.video_has_transcript(conn, ref.video_id)
    ]
    window_videos = sum(len(plan.refs) for plan in plans)
    new_videos = sum(1 for _, ref in targets if not db.video_exists(conn, ref.video_id))
    credits = min(len(targets), max(0, args.limit))
    print(f"  vídeos en ventana:            {window_videos}")
    print(f"  vídeos nuevos a transcribir:  {len(targets)} ({new_videos} sin fila previa)")
    print(f"  créditos previstos:           {credits} (1 por transcripción)")

    if args.dry_run:
        summary.notes.append("Dry-run: no se ha gastado nada.")
        summary.seconds = time.monotonic() - start
        return summary

    if not args.yes:
        answer = input("¿Lanzar la ingesta? Gasta 1 crédito por vídeo [y/N] ")
        if answer.strip().lower() not in {"y", "yes", "s", "si", "sí"}:
            summary.notes.append("Cancelado por el usuario.")
            return summary

    for plan in plans:
        channel = plan.channel
        handle = channel.get("handle") or channel.get("channel_id") or ""
        db.upsert_channel(
            conn,
            handle,
            channel.get("url", ""),
            channel.get("name", ""),
            channel.get("lang", ""),
            channel.get("channel_id", ""),
        )
    conn.commit()

    if len(targets) > credits:
        summary.notes.append(
            f"Límite de {credits} transcripciones: se posponen {len(targets) - credits} vídeos."
        )
        targets = targets[:credits]

    client = ThordataClient(settings)
    source = transcript_source(settings, client=client)
    try:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = {}
            for plan, ref in targets:
                meta = _fetch_metadata(metadata, ref, plan.channel)
                db.upsert_video(conn, meta, db.channel_id_for(conn, meta.channel_handle))
                summary.new_videos += 1
                futures[
                    pool.submit(source.fetch, ref.video_id, plan.channel.get("lang") or None)
                ] = (ref, meta)
            conn.commit()

            for future in as_completed(futures):
                ref, meta = futures[future]
                try:
                    doc = future.result()
                except CreditsExhausted as exc:
                    summary.notes.append(str(exc))
                    continue
                except (SourceError, ThordataError, TaskTimeout) as exc:
                    summary.errors += 1
                    summary.notes.append(f"{ref.video_id}: {exc}")
                    continue
                _persist_transcript(conn, doc, meta, settings, summary)
                db.record_api_call(
                    conn,
                    "thordata",
                    "youtube_transcript-by-id",
                    {"video_id": ref.video_id},
                    "ok",
                )
                summary.thordata_calls += 1
                summary.credits += 1
                print(
                    f"  ✓ {ref.video_id} [{doc.lang}] {len(doc.segments)} segmentos",
                    flush=True,
                )
                conn.commit()
    finally:
        client.close()

    idx = IndexSummary()
    build_chunks(conn, idx)
    summary.chunks = idx.chunks_created
    conn.commit()

    if args.write_seed:
        from .seed import export_seed

        count = export_seed(conn, Path(args.write_seed), target=args.seed_count)
        summary.notes.append(f"seed escrito en {args.write_seed} ({count} vídeos).")

    discovery.close()
    metadata.close()
    summary.seconds = time.monotonic() - start
    return summary


def _fetch_metadata(metadata, ref, channel: dict) -> VideoMeta:
    try:
        meta = metadata.fetch(ref.video_id)
    except SourceError:
        meta = VideoMeta(video_id=ref.video_id)
    # El handle configurado manda para el FK; el autor de oEmbed solo rellena si falta.
    configured = channel.get("handle") or channel.get("channel_id") or ""
    meta.channel_handle = configured or meta.channel_handle
    meta.channel_id = channel.get("channel_id", "")
    if channel.get("name") and not meta.channel_handle:
        meta.channel_handle = channel["name"]
    meta.lang = meta.lang or channel.get("lang", "")
    if ref.title and not meta.title:
        meta.title = ref.title
    if ref.published_at:
        meta.published_at = ref.published_at
    return meta


def _persist_transcript(
    conn, doc: TranscriptDoc, meta: VideoMeta, settings: Settings, summary: Summary
) -> None:
    if not db.video_exists(conn, doc.video_id):
        db.upsert_video(conn, meta, db.channel_id_for(conn, meta.channel_handle))
    if doc.lang:
        conn.execute("UPDATE videos SET lang=? WHERE video_id=?", (doc.lang, doc.video_id))
    raw_path = settings.db_path.parent / "raw" / f"{doc.video_id}_{doc.lang}.vtt"
    db.save_transcript(
        conn,
        doc.video_id,
        doc.lang,
        doc.subtitle_type,
        doc.segments,
        raw_path=str(raw_path) if raw_path.exists() else "",
    )
    summary.new_transcripts += 1
    summary.segments += len(doc.segments)
    summary.languages[doc.lang] = summary.languages.get(doc.lang, 0) + 1


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="radar.ingest", description="Ingesta de Radar IA")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--from-samples", action="store_true", help="carga samples locales (sin red)")
    mode.add_argument("--seed", action="store_true", help="carga seed/seed.jsonl")
    mode.add_argument("--live", action="store_true", help="fuentes reales (gasta créditos)")
    p.add_argument("--dry-run", action="store_true", help="enseña el plan y el gasto, sin gastar")
    p.add_argument("--days", type=int, default=None, help="ventana de publicación en días")
    p.add_argument("--workers", type=int, default=4, help="descargas de transcripción en paralelo")
    p.add_argument("--write-seed", default="", help="escribe seed/seed.jsonl al terminar")
    p.add_argument("--seed-count", type=int, default=18, help="vídeos en el seed")
    p.add_argument("--samples-dir", default=str(ROOT / "samples" / "panel"))
    p.add_argument("--seed-file", default=str(ROOT / "seed" / "seed.jsonl"))
    p.add_argument("--sources", default=str(ROOT / "config" / "sources.yaml"))
    p.add_argument("--limit", type=int, default=None, help="máx. transcripciones (créditos)")
    p.add_argument("-y", "--yes", action="store_true", help="no pedir confirmación")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    if args.limit is None:
        args.limit = settings.max_requests_per_run

    conn = db.connect(settings.db_path)
    db.init_db(conn)
    summary = Summary()

    if args.seed:
        ingest_seed(conn, Path(args.seed_file), summary)
    elif args.live or args.dry_run:
        if not settings.thordata_token and not args.dry_run:
            print("ERROR: falta THORDATA_TOKEN en .env")
            conn.close()
            return 2
        if not settings.thordata_token:
            print("AVISO: dry-run sin THORDATA_TOKEN (solo RSS + oEmbed).")
        ingest_live(conn, settings, load_sources(args.sources), summary, args)
    else:
        ingest_from_samples(conn, Path(args.samples_dir), summary)
    conn.commit()
    print(summary.render())
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
