"""Parseo detrás de una interfaz común.

Hay dos entradas:
  * registros *canónicos* (`seed/seed.jsonl`, tests): formato estable definido
    aquí y en `models.py`.
  * respuestas *crudas* de Thordata: se implementan contra la forma real que
    confirma el panel, sin adivinar.

Estado de la forma real (Thordata):
  - Resultado de `youtube_transcript_by-id`: CONFIRMADO. Es una lista de
    `{transcriptdownloadUrl, video_id, file_size, error, error_code}`. NO trae
    la transcripción: trae el enlace a un fichero `.vtt` (WebVTT) público.
  - Ese `.vtt`: CONFIRMADO con el fichero real de `samples/panel/`. El parser
    está en `subtitle_segments`.
  - `youtube_product_by-id` y descubrimiento: PENDIENTES de sus ejemplos.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

from .models import Channel, Segment, TranscriptDoc, VideoMeta


class ParserPendingError(RuntimeError):
    """El parser aún no está implementado (faltan samples/panel/)."""


_PENDING = (
    "Parser pendiente: falta en samples/panel/ el ejemplo real de esta respuesta "
    "de Thordata. Rellena esta función contra el JSON real; no adivines la estructura."
)


# --------------------------------------------------------------------------- #
# Resultado de youtube_transcript_by-id — CONFIRMADO EN PANEL
# --------------------------------------------------------------------------- #


@dataclass
class TranscriptTask:
    video_id: str
    download_url: str
    file_size: float = 0.0
    error: str = ""
    error_code: str = ""


def transcript_tasks_from_raw(raw) -> list[TranscriptTask]:
    """Lista de tareas de subtítulos con su enlace de descarga.

    Forma confirmada por el panel:
    `[{"transcriptdownloadUrl": "...", "video_id": "...", "file_size": 0.36,
       "error": "", "error_code": ""}, ...]`
    """
    records = raw
    if isinstance(raw, dict):
        for key in ("data", "result", "results"):
            if isinstance(raw.get(key), list):
                records = raw[key]
                break
    if not isinstance(records, list):
        raise ParserPendingError(_PENDING)

    tasks: list[TranscriptTask] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        url = record.get("transcriptdownloadUrl") or record.get("transcript_download_url")
        video_id = record.get("video_id")
        if not url or not video_id:
            continue
        tasks.append(
            TranscriptTask(
                video_id=str(video_id),
                download_url=str(url),
                file_size=float(record.get("file_size") or 0),
                error=str(record.get("error") or ""),
                error_code=str(record.get("error_code") or ""),
            )
        )
    return tasks


_SUBTITLE_NAME = re.compile(
    r"(?P<video_id>[A-Za-z0-9_-]{11})_(?P<lang>[\w-]+?)(?:_subtitle)?\.(?:txt|vtt|srt)$",
    re.IGNORECASE,
)


def subtitle_filename_parts(filename: str) -> tuple[str, str] | None:
    """Extrae (video_id, lang) del nombre tipo `8RePenzQH80_en.vtt` del panel."""
    match = _SUBTITLE_NAME.search(filename)
    return (match.group("video_id"), match.group("lang")) if match else None


# WebVTT: `HH:MM:SS.mmm` o `MM:SS.mmm` (la hora es opcional).
_TS = r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[.,](\d{1,3})"
_CUE_TIMING = re.compile(rf"^\s*{_TS}\s*-->\s*{_TS}(?:\s+.*)?$")
# Timestamps por palabra tipo <00:00:01.234> y etiquetas inline <c>, </c>, <v Ana>.
_INLINE_WORD_TS = re.compile(r"<\d{1,2}:\d{2}:\d{2}[.,]\d{1,3}>")
_INLINE_TAG = re.compile(r"</?[^>]+>")


def _groups_to_ms(groups: tuple) -> int:
    hours, minutes, seconds, fraction = groups
    ms = int(str(fraction).ljust(3, "0")[:3])
    return ((int(hours or 0) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + ms


def _parse_timing(line: str) -> tuple[int, int] | None:
    match = _CUE_TIMING.match(line)
    if not match:
        return None
    groups = match.groups()
    return _groups_to_ms(groups[:4]), _groups_to_ms(groups[4:8])


def _clean_cue_text(raw: str) -> str:
    text = _INLINE_WORD_TS.sub("", raw)
    text = _INLINE_TAG.sub("", text)
    text = html.unescape(text).replace("\u200b", "")
    return re.sub(r"\s+", " ", text).strip()


def _strip_overlap(previous: str, current: str) -> str:
    """Quita del inicio de `current` el solape con el final de `previous`.

    Los subtítulos automáticos de YouTube son de scroll: cada cue repite la(s)
    línea(s) anterior(es). Sin esto el texto sale duplicado y los embeddings
    quedan inservibles.
    """
    if not previous or not current:
        return current
    prev_words = previous.split()
    cur_words = current.split()
    for size in range(min(len(prev_words), len(cur_words)), 0, -1):
        if prev_words[-size:] == cur_words[:size]:
            return " ".join(cur_words[size:])
    return current


def subtitle_segments(content: str, video_id: str = "", lang: str = "") -> list[Segment]:
    """Segmentos (start_ms, end_ms, text) a partir de un fichero WebVTT."""
    lines = content.lstrip("\ufeff").splitlines()
    segments: list[Segment] = []
    previous = ""
    index = 0
    total = len(lines)
    while index < total:
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        upper = line.upper()
        if upper.startswith(("WEBVTT", "KIND:", "LANGUAGE:")):
            index += 1
            continue
        if upper.startswith(("NOTE", "STYLE", "REGION")):
            index += 1
            while index < total and lines[index].strip():
                index += 1
            continue
        timing = _parse_timing(line)
        if timing is None:
            index += 1  # identificador de cue u otra línea suelta
            continue
        start_ms, end_ms = timing
        index += 1
        raw_lines = []
        while index < total and lines[index].strip():
            raw_lines.append(lines[index])
            index += 1
        text = _strip_overlap(previous, _clean_cue_text(" ".join(raw_lines)))
        if not text:
            continue
        segments.append(Segment(start_ms=start_ms, end_ms=end_ms, text=text))
        previous = text
    return segments


# --------------------------------------------------------------------------- #
# Respuestas crudas aún sin ejemplo: SIN CONFIRMAR
# --------------------------------------------------------------------------- #


def video_from_raw(raw: dict) -> VideoMeta:
    raise ParserPendingError(_PENDING)


def discovery_from_raw(raw: dict) -> list[dict]:
    raise ParserPendingError(_PENDING)


# --------------------------------------------------------------------------- #
# Formato canónico (seed/seed.jsonl y tests)
# --------------------------------------------------------------------------- #


def _optional_int(value) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def channel_from_record(obj: dict) -> Channel:
    return Channel(
        handle=obj.get("handle", ""),
        url=obj.get("url", ""),
        name=obj.get("name", ""),
        lang=obj.get("lang", ""),
        channel_id=obj.get("channel_id", ""),
    )


def video_from_record(obj: dict) -> VideoMeta:
    return VideoMeta(
        video_id=obj["video_id"],
        channel_handle=obj.get("channel_handle", ""),
        channel_id=obj.get("channel_id", ""),
        title=obj.get("title", ""),
        description=obj.get("description", ""),
        published_at=obj.get("published_at", ""),
        duration_s=_optional_int(obj.get("duration_s")),
        view_count=_optional_int(obj.get("view_count")),
        like_count=_optional_int(obj.get("like_count")),
        lang=obj.get("lang", ""),
        url=obj.get("url", ""),
        thumbnail_url=obj.get("thumbnail_url", ""),
    )


def transcript_from_record(obj: dict) -> TranscriptDoc:
    segments = [
        Segment(
            start_ms=int(s["start_ms"]),
            end_ms=int(s["end_ms"]),
            text=str(s.get("text", "")),
        )
        for s in obj.get("segments", [])
    ]
    return TranscriptDoc(
        video_id=obj["video_id"],
        lang=obj.get("lang", ""),
        subtitle_type=obj.get("subtitle_type", "unknown"),
        segments=segments,
    )
