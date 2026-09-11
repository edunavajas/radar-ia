"""Descubrimiento por el feed RSS público de YouTube (gratis, sin API key).

`GET https://www.youtube.com/feeds/videos.xml?channel_id=UC...` devuelve los
últimos ~15 vídeos del canal. Soporta también `?playlist_id=` y `?user=`.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from . import SourceError, VideoRef
from .http import CachedHttp

RSS_URL = "https://www.youtube.com/feeds/videos.xml"
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}
_CHANNEL_ID_RE = re.compile(
    r'"(?:channelId|externalId|browseId)":"(UC[\w-]{22})"'
    r'|itemprop="identifier"\s+content="(UC[\w-]{22})"'
)
_CHANNEL_ID_ONLY = re.compile(r"^UC[\w-]{22}$")


def feed_url(channel_id: str = "", playlist_id: str = "", user: str = "") -> str:
    if channel_id:
        return f"{RSS_URL}?channel_id={channel_id}"
    if playlist_id:
        return f"{RSS_URL}?playlist_id={playlist_id}"
    if user:
        return f"{RSS_URL}?user={user}"
    raise SourceError("El feed necesita channel_id, playlist_id o user")


def parse_feed(xml_text: str) -> list[VideoRef]:
    root = ET.fromstring(xml_text)
    videos: list[VideoRef] = []
    for entry in root.findall("atom:entry", _NS):
        video_id = entry.findtext("yt:videoId", default="", namespaces=_NS)
        if not video_id:
            continue
        link = ""
        for link_el in entry.findall("atom:link", _NS):
            if link_el.get("rel") == "alternate":
                link = link_el.get("href", "")
                break
        videos.append(
            VideoRef(
                video_id=video_id,
                title=entry.findtext("atom:title", default="", namespaces=_NS),
                published_at=entry.findtext("atom:published", default="", namespaces=_NS),
                channel_handle=entry.findtext("atom:author/atom:name", default="", namespaces=_NS),
                url=link,
            )
        )
    return videos


def extract_channel_id(page_html: str) -> str | None:
    match = _CHANNEL_ID_RE.search(page_html)
    if not match:
        return None
    return next((group for group in match.groups() if group), None)


class YouTubeRSSDiscovery:
    name = "youtube_rss"

    def __init__(self, http: CachedHttp):
        self.http = http

    def discover(self, channel: dict) -> list[VideoRef]:
        url = feed_url(
            channel_id=channel.get("channel_id", ""),
            playlist_id=channel.get("playlist_id", ""),
            user=channel.get("user", ""),
        )
        refs = parse_feed(self.http.get_text(url, "rss"))
        for ref in refs:
            ref.channel_id = channel.get("channel_id", "")
            if channel.get("handle"):
                ref.channel_handle = channel["handle"]
        return refs

    def resolve_channel_id(self, handle_or_url: str) -> str:
        """Resuelve `@handle` (o URL de canal) a `UC...` leyendo el HTML."""
        target = handle_or_url.strip()
        if _CHANNEL_ID_ONLY.match(target):
            return target
        if target.startswith("http"):
            url = target
        else:
            url = "https://www.youtube.com/" + (
                target if target.startswith("@") else f"@{target}"
            )
        page = self.http.get_text(url, "channel")
        channel_id = extract_channel_id(page)
        if not channel_id:
            raise SourceError(f"No pude resolver el channel_id de {handle_or_url!r}")
        return channel_id

    def close(self) -> None:
        self.http.close()
