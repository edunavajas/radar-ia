"""Modelos canónicos que usa todo el sistema.

El JSON crudo de las APIs se normaliza a estos tipos en los parsers y fuentes,
de modo que cambiar un campo se toca en un único sitio.

`duration_s`, `view_count` y `like_count` son opcionales: la vía gratuita
(oEmbed) no los da. Se dejan en `None`; nunca se inventan ni se ponen a cero.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Channel:
    handle: str = ""
    url: str = ""
    name: str = ""
    lang: str = ""
    channel_id: str = ""


@dataclass
class VideoMeta:
    video_id: str
    channel_handle: str = ""
    channel_id: str = ""
    title: str = ""
    description: str = ""
    published_at: str = ""
    duration_s: int | None = None
    view_count: int | None = None
    like_count: int | None = None
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
