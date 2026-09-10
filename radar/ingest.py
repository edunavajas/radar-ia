"""Ingesta: llena la base de datos desde samples locales, seed o la API real.

Modos:
  --from-samples  (por defecto) lee ficheros locales, no toca la red.
  --seed          carga seed/seed.jsonl (formato canónico).
  --live          ciclo real contra Thordata (gasta créditos).

Reglas de coste: deduplicación por video_id, límite duro de peticiones por
ejecución, confirmación antes de gastar y resumen final de llamadas.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import db, spiders
from .config import ROOT, Settings, get_settings
from .models import TranscriptDoc
from .parsers import (
    ParserPendingError,
    channel_from_record,
    discovery_from_raw,
    subtitle_filename_parts,
    subtitle_segments,
    transcript_from_record,
    transcript_tasks_from_raw,
    video_from_raw,
    video_from_record,
)
from .thordata import CreditsExhausted, TaskTimeout, ThordataClient, ThordataError

SUBTITLE_SUFFIXES = {".txt", ".vtt", ".srt"}


@dataclass
class Summary:
    new_videos: int = 0
    new_transcripts: int = 0
    chunks: int = 0
    requests: int = 0
    thordata_calls: int = 0
    ai_calls: int = 0
    skipped: int = 0
    notes: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            "Resumen de ingesta:",
            f"  vídeos nuevos:        {self.new_videos}",
            f"  transcripciones:      {self.new_transcripts}",
            f"  chunks:               {self.chunks}",
            f"  peticiones Thordata:  {self.thordata_calls}",
            f"  peticiones IA:        {self.ai_calls}",
            f"  omitidos (ya estaban):{self.skipped}",
        ]
        lines += [f"  nota: {n}" for n in self.notes]
        return "\n".join(lines)


def load_sources(path: Path | str = ROOT / "config" / "sources.yaml") -> dict:
    path = Path(path)
    if not path.exists():
        return {"channels": [], "keywords": [], "languages_fallback": ["en-orig", "en"]}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


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
                    f"{path.name}: {task.video_id} apunta a un .txt que no está en "
                    f"{path.parent.name}/ (el JSON solo trae el enlace)"
                )
        return
    _store_video(conn, video_from_raw(raw), summary)


def _ingest_subtitle_sample(conn, path: Path, summary: Summary) -> None:
    parts = subtitle_filename_parts(path.name)
    if not parts:
        summary.notes.append(f"{path.name}: no pude deducir video_id/idioma del nombre")
        return
    video_id, lang = parts
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
        isinstance(record, dict) and record.get("transcriptdownloadUrl")
        for record in records
    )


def _store_video(conn, meta, summary: Summary) -> None:
    if db.video_exists(conn, meta.video_id):
        summary.skipped += 1
    else:
        summary.new_videos += 1
    channel_id = db.channel_id_for(conn, meta.channel_handle)
    db.upsert_video(conn, meta, channel_id)


def _store_transcript(conn, doc, raw_path: Path | None, summary: Summary) -> None:
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
            db.upsert_channel(conn, ch.handle, ch.url, ch.name, ch.lang)
        elif kind == "video":
            meta = video_from_record(obj)
            if not db.video_exists(conn, meta.video_id):
                summary.new_videos += 1
            channel_id = db.channel_id_for(conn, meta.channel_handle)
            db.upsert_video(conn, meta, channel_id)
        elif kind == "transcript":
            doc = transcript_from_record(obj)
            if db.has_transcript(conn, doc.video_id, doc.lang, doc.subtitle_type):
                summary.skipped += 1
            else:
                db.save_transcript(
                    conn, doc.video_id, doc.lang, doc.subtitle_type, doc.segments
                )
                summary.new_transcripts += 1
        else:
            summary.notes.append(f"seed: tipo desconocido {kind!r}")
    conn.commit()
    return summary


# --------------------------------------------------------------------------- #
# Modo live
# --------------------------------------------------------------------------- #


def planned_discovery_requests(sources: dict) -> list[dict]:
    reqs = []
    for ch in sources.get("channels", []) or []:
        reqs.append(
            spiders.channel_videos_request(
                ch["url"], int(ch.get("max_posts", 15))
            )
        )
    for kw in sources.get("keywords", []) or []:
        reqs.append(
            spiders.search_request(
                kw["query"],
                upload_date=kw.get("upload_date", ""),
            )
        )
    return reqs


def ingest_live(
    conn, settings: Settings, sources: dict, summary: Summary, assume_yes: bool
) -> Summary:
    discovery = planned_discovery_requests(sources)
    limit = settings.max_requests_per_run
    print(f"Peticiones de descubrimiento previstas: {len(discovery)}")
    print(f"Límite duro por ejecución: {limit}")
    if not assume_yes:
        answer = input("¿Lanzar la ingesta? Gasta créditos [y/N] ").strip().lower()
        if answer not in {"y", "yes", "s", "si", "sí"}:
            summary.notes.append("Cancelado por el usuario.")
            return summary

    with ThordataClient(settings) as client:
        for req in discovery:
            if summary.requests >= limit:
                summary.notes.append("Límite de peticiones alcanzado.")
                break
            try:
                task_id = client.launch(req)
                raw = settings.db_path.parent / "raw" / f"{task_id}.json"
                client.poll_and_save(task_id, raw)
                summary.requests += 1
                db.record_api_call(conn, "thordata", req["spider_id"], req, "ok")
                summary.thordata_calls += 1
                payload = json.loads(Path(raw).read_text(encoding="utf-8"))
                for ref in discovery_from_raw(payload):
                    video_id = ref["video_id"]
                    if db.video_exists(conn, video_id):
                        summary.skipped += 1
                        continue
                    _ingest_video_live(
                        conn, client, settings, video_id, summary, limit
                    )
            except CreditsExhausted as exc:
                summary.notes.append(str(exc))
                break
            except ParserPendingError as exc:
                summary.notes.append(str(exc))
                break
            except (ThordataError, TaskTimeout) as exc:
                summary.notes.append(f"Error en descubrimiento: {exc}")
                db.record_api_call(conn, "thordata", req["spider_id"], req, "error")
                continue
    conn.commit()
    return summary


def _ingest_video_live(conn, client, settings: Settings, video_id: str, summary: Summary, limit: int) -> None:
    if summary.requests + 2 > limit:
        summary.notes.append(f"Límite alcanzado antes de {video_id}.")
        return
    try:
        meta_req = spiders.video_request(video_id)
        task = client.launch(meta_req)
        raw = settings.db_path.parent / "raw" / f"{video_id}-meta.json"
        client.poll_and_save(task, raw)
        summary.requests += 1
        db.record_api_call(conn, "thordata", meta_req["spider_id"], meta_req, "ok")
        summary.thordata_calls += 1
        meta = video_from_raw(json.loads(Path(raw).read_text(encoding="utf-8")))
        _store_video(conn, meta, summary)

        tr_req = spiders.transcript_request(video_id)
        task = client.launch(tr_req)
        raw = settings.db_path.parent / "raw" / f"{video_id}-transcript.json"
        client.poll_and_save(task, raw)
        summary.requests += 1
        db.record_api_call(conn, "thordata", tr_req["spider_id"], tr_req, "ok")
        summary.thordata_calls += 1

        # El JSON del panel no trae la transcripción: trae el enlace al .txt.
        tasks = transcript_tasks_from_raw(
            json.loads(Path(raw).read_text(encoding="utf-8"))
        )
        matched = next(
            (t for t in tasks if t.video_id == video_id), tasks[0] if tasks else None
        )
        if matched is None:
            summary.notes.append(f"{video_id}: sin enlace de subtítulos")
            return
        if matched.error:
            summary.notes.append(
                f"{video_id}: subtítulos con error {matched.error_code} {matched.error}".strip()
            )
            return

        parts = subtitle_filename_parts(matched.download_url)
        lang = parts[1] if parts else (meta.lang or "en")
        subtitle_text = client.fetch_text(matched.download_url)
        subtitle_path = settings.db_path.parent / "raw" / f"{video_id}_{lang}.txt"
        subtitle_path.parent.mkdir(parents=True, exist_ok=True)
        subtitle_path.write_text(subtitle_text, encoding="utf-8")

        segments = subtitle_segments(subtitle_text, video_id, lang)
        doc = TranscriptDoc(
            video_id=video_id,
            lang=lang,
            subtitle_type="auto_generated",
            segments=segments,
        )
        _store_transcript(conn, doc, subtitle_path, summary)
    except CreditsExhausted:
        raise
    except ParserPendingError:
        raise
    except (ThordataError, TaskTimeout) as exc:
        summary.notes.append(f"{video_id}: {exc}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="radar.ingest", description="Ingesta de Radar IA")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--from-samples", action="store_true", help="carga samples locales (sin red)")
    mode.add_argument("--seed", action="store_true", help="carga seed/seed.jsonl")
    mode.add_argument("--live", action="store_true", help="ciclo real contra Thordata")
    p.add_argument("--samples-dir", default=str(ROOT / "samples" / "panel"))
    p.add_argument("--seed-file", default=str(ROOT / "seed" / "seed.jsonl"))
    p.add_argument("--sources", default=str(ROOT / "config" / "sources.yaml"))
    p.add_argument("--limit", type=int, default=None, help="sobrescribe MAX_REQUESTS_PER_RUN")
    p.add_argument("-y", "--yes", action="store_true", help="no pedir confirmación")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    if args.limit is not None:
        object.__setattr__(settings, "max_requests_per_run", args.limit)

    conn = db.connect(settings.db_path)
    db.init_db(conn)
    summary = Summary()

    if args.seed:
        ingest_seed(conn, Path(args.seed_file), summary)
    elif args.live:
        if not settings.thordata_token:
            print("ERROR: falta THORDATA_TOKEN en .env")
            conn.close()
            return 2
        ingest_live(conn, settings, load_sources(args.sources), summary, args.yes)
    else:  # por defecto, samples locales
        ingest_from_samples(conn, Path(args.samples_dir), summary)
    conn.commit()
    print(summary.render())
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
