"""Metadatos por oEmbed público de YouTube (gratis, sin credenciales).

`GET https://www.youtube.com/oembed?url=...&format=json` da título, nombre del
canal, URL del canal y miniatura. Duración, vistas y likes NO están disponibles
por esta vía: se dejan en `None` y la UI no los pinta.
"""

from __future__ import annotations

import json
from urllib.parse import quote

from ..models import VideoMeta
from . import SourceError
from .http import CachedHttp

OEMBED_URL = "https://www.youtube.com/oembed"


def oembed_url(video_id: str) -> str:
    watch = f"https://www.youtube.com/watch?v={video_id}"
    return f"{OEMBED_URL}?url={quote(watch, safe='')}&format=json"


class YouTubeOEmbedMetadata:
    name = "youtube_oembed"

    def __init__(self, http: CachedHttp):
        self.http = http

    def fetch(self, video_id: str) -> VideoMeta:
        watch = f"https://www.youtube.com/watch?v={video_id}"
        try:
            data = json.loads(self.http.get_text(oembed_url(video_id), "oembed"))
        except Exception as exc:  # noqa: BLE001 - se traduce a un error de fuente
            raise SourceError(f"oEmbed no disponible para {video_id}: {exc}") from exc
        thumbnail = data.get("thumbnail_url") or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        return VideoMeta(
            video_id=video_id,
            title=data.get("title", ""),
            channel_handle=data.get("author_name", ""),
            description="",
            thumbnail_url=thumbnail,
            url=watch,
        )

    def close(self) -> None:
        self.http.close()
