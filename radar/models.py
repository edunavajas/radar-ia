"""Modelos canónicos que usa todo el sistema.

El JSON crudo de las APIs se normaliza a estos tipos en `parsers.py`, de modo
que cambiar un campo de la respuesta se toca en un único sitio.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Channel:
    handle: str
    url: str
    name: str = ""
    lang: str = ""


@dataclass
class VideoMeta:
    video_id: str
    channel_handle: str = ""
    title: str = ""
    description: str = ""
    published_at: str = ""
    duration_s: int = 0
    view_count: int = 0
    lang: str = ""
    url: str = ""
    thumbnail_url: str = ""

    def __post_init__(self) -> None:
        if not self.url:
            self.url = f"https://www.youtube.com/watch?v={self.video_id}"
        if not self.thumbnail_url:
            self.thumbnail_url = f"https://i.ytimg.com/vi/{self.video_id}/hqdefault.jpg"


@dataclass
class Segment:
    start_ms: int
    end_ms: int
    text: str


@dataclass
class TranscriptDoc:
    video_id: str
    lang: str
    subtitle_type: str
    segments: list[Segment] = field(default_factory=list)


@dataclass
class Chunk:
    video_id: str
    start_ms: int
    end_ms: int
    text: str
    token_count: int = 0
