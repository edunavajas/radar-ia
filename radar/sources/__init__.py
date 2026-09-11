"""Fuentes de datos detrás de una interfaz común, un módulo por proveedor.

- Transcripciones (de pago): Thordata `youtube_transcript_by-id`. Donde no hay
  alternativa: transcripciones a escala sin bloqueos. Módulo:
  `thordata_transcripts`.
- Descubrimiento (gratis): feed RSS público de YouTube. Módulo: `youtube_rss`.
- Metadatos (gratis): oEmbed público de YouTube. Módulo: `youtube_oembed`.

Cambiar de proveedor = cambiar la implementación de estos protocolos; la ingesta
no se toca.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import TranscriptDoc, VideoMeta


class SourceError(RuntimeError):
    pass


@dataclass
class VideoRef:
    """Referencia mínima de un vídeo descubierto (sin metadatos completos)."""

    video_id: str
    title: str = ""
    published_at: str = ""
    channel_handle: str = ""
    channel_id: str = ""
    url: str = ""


class DiscoverySource:
    name = "discovery"

    def discover(self, channel: dict) -> list[VideoRef]:  # pragma: no cover - protocolo
        raise NotImplementedError


class MetadataSource:
    name = "metadata"

    def fetch(self, video_id: str) -> VideoMeta:  # pragma: no cover - protocolo
        raise NotImplementedError


class TranscriptSource:
    name = "transcript"

    def fetch(self, video_id: str, lang: str | None = None) -> TranscriptDoc:  # pragma: no cover
        raise NotImplementedError


def make_http(settings, min_interval: float = 0.5):
    from .http import CachedHttp

    return CachedHttp(
        cache_dir=settings.db_path.parent / "http_cache",
        min_interval=min_interval,
    )


def discovery_source(settings) -> "DiscoverySource":
    from .youtube_rss import YouTubeRSSDiscovery

    return YouTubeRSSDiscovery(make_http(settings))


def metadata_source(settings) -> "MetadataSource":
    from .youtube_oembed import YouTubeOEmbedMetadata

    return YouTubeOEmbedMetadata(make_http(settings))


def transcript_source(settings, client=None) -> "TranscriptSource":
    from .thordata_transcripts import ThordataTranscriptSource

    return ThordataTranscriptSource(settings, client=client)
