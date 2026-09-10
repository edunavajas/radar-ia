from __future__ import annotations

import pytest

from radar.parsers import (
    ParserPendingError,
    channel_from_record,
    transcript_from_raw,
    transcript_from_record,
    video_from_record,
)


def test_channel_from_record() -> None:
    ch = channel_from_record(
        {"handle": "@ejemplo", "url": "https://youtube.com/@ejemplo/videos", "lang": "en"}
    )
    assert ch.handle == "@ejemplo"
    assert ch.lang == "en"


def test_video_from_record_defaults_url_and_thumbnail() -> None:
    v = video_from_record({"video_id": "abc123", "title": "Hola"})
    assert v.url == "https://www.youtube.com/watch?v=abc123"
    assert v.thumbnail_url == "https://i.ytimg.com/vi/abc123/hqdefault.jpg"


def test_transcript_from_record_preserves_timestamps() -> None:
    doc = transcript_from_record(
        {
            "video_id": "abc123",
            "lang": "zh-Hans",
            "subtitle_type": "auto_generated",
            "segments": [
                {"start_ms": 0, "end_ms": 2500, "text": "你好"},
                {"start_ms": 2500, "end_ms": 5000, "text": "世界"},
            ],
        }
    )
    assert doc.lang == "zh-Hans"
    assert [s.start_ms for s in doc.segments] == [0, 2500]
    assert doc.segments[1].text == "世界"


def test_raw_parser_is_explicitly_pending() -> None:
    # Fase 1 (samples/panel/) todavía no está disponible: no se adivina.
    with pytest.raises(ParserPendingError):
        transcript_from_raw({"whatever": "shape"})
