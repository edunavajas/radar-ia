from __future__ import annotations

import time

import pytest

from radar.sources import SourceError
from radar.sources.http import CachedHttp
from radar.sources.youtube_oembed import YouTubeOEmbedMetadata, oembed_url
from radar.sources.youtube_rss import (
    YouTubeRSSDiscovery,
    extract_channel_id,
    feed_url,
    parse_feed,
)

CHANNEL_ID = "UC" + "a" * 22

RSS_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
 <entry>
  <id>yt:video:abc12345678</id>
  <yt:videoId>abc12345678</yt:videoId>
  <title>Hola mundo</title>
  <published>2026-09-10T10:00:00+00:00</published>
  <author><name>Canal de prueba</name></author>
  <link rel="alternate" href="https://www.youtube.com/watch?v=abc12345678"/>
 </entry>
</feed>
"""


def test_feed_url_variants() -> None:
    assert feed_url(channel_id=CHANNEL_ID).endswith(f"?channel_id={CHANNEL_ID}")
    assert "playlist_id=PL1" in feed_url(playlist_id="PL1")
    assert "user=algo" in feed_url(user="algo")
    with pytest.raises(SourceError):
        feed_url()


def test_parse_feed() -> None:
    refs = parse_feed(RSS_XML)
    assert len(refs) == 1
    ref = refs[0]
    assert ref.video_id == "abc12345678"
    assert ref.title == "Hola mundo"
    assert ref.published_at.startswith("2026-09-10")
    assert ref.channel_handle == "Canal de prueba"
    assert ref.url.endswith("watch?v=abc12345678")


def test_extract_channel_id() -> None:
    html = f'<html><script>var x={{"channelId":"{CHANNEL_ID}"}};</script></html>'
    assert extract_channel_id(html) == CHANNEL_ID
    assert extract_channel_id("<html>nada</html>") is None


def test_channel_resolution_uses_html(tmp_path) -> None:
    http = CachedHttp(tmp_path, fetch=lambda url: f'"channelId":"{CHANNEL_ID}"'.encode())
    discovery = YouTubeRSSDiscovery(http)
    assert discovery.resolve_channel_id("@midudev") == CHANNEL_ID
    assert discovery.resolve_channel_id(CHANNEL_ID) == CHANNEL_ID


def test_oembed_metadata(tmp_path) -> None:
    payload = b'{"title":"Un video","author_name":"Canal","thumbnail_url":"https://t/img.jpg"}'
    http = CachedHttp(tmp_path, fetch=lambda url: payload)
    meta = YouTubeOEmbedMetadata(http).fetch("abc12345678")
    assert meta.title == "Un video"
    assert meta.channel_handle == "Canal"
    assert meta.thumbnail_url == "https://t/img.jpg"
    assert meta.duration_s is None and meta.view_count is None and meta.like_count is None


def test_oembed_url_encodes_watch_url() -> None:
    url = oembed_url("abc12345678")
    assert url.startswith("https://www.youtube.com/oembed?url=")
    assert "%3A%2F%2F" in url and "format=json" in url


def test_http_cache_avoids_second_fetch(tmp_path) -> None:
    calls = {"n": 0}

    def fetch(url):
        calls["n"] += 1
        return b"contenido"

    http = CachedHttp(tmp_path, min_interval=0.0, fetch=fetch)
    assert http.get("https://x/1", "rss") == b"contenido"
    assert http.get("https://x/1", "rss") == b"contenido"
    assert calls["n"] == 1


def test_http_rate_limit_spaces_requests(tmp_path) -> None:
    http = CachedHttp(tmp_path, min_interval=0.2, fetch=lambda url: b"x")
    start = time.monotonic()
    http.get("https://x/a", "rss")
    http.get("https://x/b", "rss")
    assert time.monotonic() - start >= 0.2
