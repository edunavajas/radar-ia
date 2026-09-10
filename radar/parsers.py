"""Parseo detrás de una interfaz común.

Hay dos entradas:
  * registros *canónicos* (`seed/seed.jsonl`, tests): formato estable definido
    aquí y en `models.py`.
  * respuestas *crudas* de Thordata: se implementan contra la forma real que
    confirma el panel, sin adivinar.

Estado de la forma real (Thordata):
  - Resultado de `youtube_transcript_by-id`: CONFIRMADO por el panel. Es una
    lista de `{transcriptdownloadUrl, video_id, file_size, error, error_code}`.
    NO trae la transcripción: trae el enlace a un fichero `.txt`.
  - Formato interno de ese `.txt`: PENDIENTE. Falta un fichero real de
    `samples/panel/`; no se adivina.
  - `youtube_product_by-id` y descubrimiento: PENDIENTES de sus ejemplos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Channel, Segment, TranscriptDoc, VideoMeta


class ParserPendingError(RuntimeError):
    """El parser aún no está implementado (faltan samples/panel/)."""


_PENDING = (
    "Parser pendiente: falta en samples/panel/ el ejemplo real de esta respuesta "
    "de Thordata. Rellena esta función contra el JSON real; no adivines la estructura."
)

_SUBTITLE_PENDING = (
    "Formato del fichero de subtítulos (.txt) sin confirmar: el resultado JSON de "
    "youtube_transcript_by-id solo trae el enlace (transcriptdownloadUrl); el texto "
    "con sus tiempos viene dentro del .txt. Falta un fichero real en samples/panel/."
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
    r"(?P<video_id>[\w-]{6,})_(?P<lang>[\w-]+)\.(?:txt|vtt|srt)$", re.IGNORECASE
)


def subtitle_filename_parts(filename: str) -> tuple[str, str] | None:
    """Extrae (video_id, lang) del nombre tipo `8RePenzQH80_en.txt` del panel."""
    match = _SUBTITLE_NAME.search(filename)
    return (match.group("video_id"), match.group("lang")) if match else None


def subtitle_segments(content: str, video_id: str = "", lang: str = "") -> list[Segment]:
    """Segmentos con tiempos a partir del `.txt` de subtítulos. PENDIENTE."""
    raise ParserPendingError(_SUBTITLE_PENDING)


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


def channel_from_record(obj: dict) -> Channel:
    return Channel(
        handle=obj.get("handle", ""),
        url=obj.get("url", ""),
        name=obj.get("name", ""),
        lang=obj.get("lang", ""),
    )


def video_from_record(obj: dict) -> VideoMeta:
    return VideoMeta(
        video_id=obj["video_id"],
        channel_handle=obj.get("channel_handle", ""),
        title=obj.get("title", ""),
        description=obj.get("description", ""),
        published_at=obj.get("published_at", ""),
        duration_s=int(obj.get("duration_s", 0) or 0),
        view_count=int(obj.get("view_count", 0) or 0),
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
