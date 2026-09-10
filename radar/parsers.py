"""Parseo detrás de una interfaz común.

Hay dos entradas:
  * registros *canónicos* (`seed/seed.jsonl`, tests): formato estable definido
    aquí y en `models.py`.
  * respuestas *crudas* de Thordata: su forma exacta todavía no está
    confirmada porque faltan los ficheros de `samples/panel/`. Las funciones
    `*_raw` están deliberadamente sin implementar: no se adivina la estructura.
    Cuando existan los samples, se rellenan ÚNICAMENTE estas funciones.
"""

from __future__ import annotations

from .models import Channel, Segment, TranscriptDoc, VideoMeta


class ParserPendingError(RuntimeError):
    """El parser crudo aún no está implementado (faltan samples/panel/)."""


_PENDING = (
    "Parser pendiente: falta samples/panel/ con la respuesta real de Thordata. "
    "Rellena esta función contra el JSON real; no adivines la estructura."
)


# --------------------------------------------------------------------------- #
# Respuestas crudas de Thordata — SIN CONFIRMAR (dependen de samples/panel/)
# --------------------------------------------------------------------------- #


def transcript_from_raw(raw: dict) -> TranscriptDoc:
    raise ParserPendingError(_PENDING)


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
