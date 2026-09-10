from __future__ import annotations

import json
from pathlib import Path

import pytest

from radar.parsers import (
    ParserPendingError,
    channel_from_record,
    subtitle_filename_parts,
    subtitle_segments,
    transcript_from_record,
    transcript_tasks_from_raw,
    video_from_record,
)

PANEL_DIR = Path(__file__).resolve().parent.parent / "samples" / "panel"


def test_transcript_tasks_from_real_panel_example() -> None:
    raw = json.loads((PANEL_DIR / "transcript_result.example.json").read_text())
    tasks = transcript_tasks_from_raw(raw)
    assert len(tasks) == 4
    first = tasks[0]
    assert first.video_id == "8RePenzQH80"
    assert first.download_url.endswith("8RePenzQH80_en.txt")
    assert first.file_size == 0.36
    assert first.error == ""


def test_transcript_tasks_unwraps_dict_envelope() -> None:
    raw = {
        "code": 200,
        "data": [{"video_id": "x", "transcriptdownloadUrl": "https://a/b_x_en.txt"}],
    }
    assert transcript_tasks_from_raw(raw)[0].download_url.endswith("b_x_en.txt")


def test_subtitle_filename_parts_from_urls() -> None:
    url = "https://data.thordata.com/x/8RePenzQH80_en.txt"
    assert subtitle_filename_parts(url) == ("8RePenzQH80", "en")
    assert subtitle_filename_parts("aO2Th8rs-e8_zh-Hans.txt") == ("aO2Th8rs-e8", "zh-Hans")
    assert subtitle_filename_parts("nope.json") is None


def test_subtitle_content_parser_is_explicitly_pending() -> None:
    # El formato interno del .txt todavía no está confirmado: no se adivina.
    with pytest.raises(ParserPendingError):
        subtitle_segments("lo que sea", "8RePenzQH80", "en")


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
