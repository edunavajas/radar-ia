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
    video_from_raw,
    video_from_record,
)

PANEL_DIR = Path(__file__).resolve().parent.parent / "samples" / "panel"
REAL_VTT = PANEL_DIR / "8RePenzQH80_en.vtt"


# --------------------------------------------------------------------------- #
# Resultado de youtube_transcript_by-id (confirmado)
# --------------------------------------------------------------------------- #


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
    url = "https://new-data.thordata.com/x/8RePenzQH80_en.vtt"
    assert subtitle_filename_parts(url) == ("8RePenzQH80", "en")
    assert subtitle_filename_parts("aO2Th8rs-e8_zh-Hans.vtt") == ("aO2Th8rs-e8", "zh-Hans")
    assert subtitle_filename_parts("nope.json") is None


def test_unconfirmed_raw_parsers_are_pending() -> None:
    with pytest.raises(ParserPendingError):
        video_from_raw({"x": 1})


# --------------------------------------------------------------------------- #
# Parser WebVTT
# --------------------------------------------------------------------------- #


def test_real_vtt_parses_with_timestamps_and_clean_text() -> None:
    segments = subtitle_segments(REAL_VTT.read_text(encoding="utf-8"))
    assert len(segments) > 50
    first = segments[0]
    assert first.start_ms == 160
    assert first.end_ms == 4000
    assert first.text.startswith("Now, as we've been discussing")
    joined = " ".join(s.text for s in segments)
    assert "&nbsp;" not in joined
    assert "<" not in joined and ">" not in joined
    assert all(a.start_ms <= b.start_ms for a, b in zip(segments, segments[1:]))


def test_real_vtt_text_is_not_repeated() -> None:
    segments = subtitle_segments(REAL_VTT.read_text(encoding="utf-8"))
    for previous, current in zip(segments, segments[1:]):
        if len(previous.text) > 20:
            assert not current.text.startswith(previous.text)


def test_scroll_captions_are_deduplicated() -> None:
    vtt = (
        "WEBVTT\n\n"
        "00:00:00.000 --> 00:00:03.000\nHello world\nthis is line two\n\n"
        "00:00:03.000 --> 00:00:06.000\nthis is line two\nand line three\n\n"
    )
    segments = subtitle_segments(vtt)
    assert [s.text for s in segments] == ["Hello world this is line two", "and line three"]


def test_inline_tags_and_word_timestamps_are_removed() -> None:
    vtt = (
        "WEBVTT\n\n"
        "00:00:00.000 --> 00:00:02.000\n"
        "<c>Hola</c> <00:00:01.000>mundo&nbsp;\n"
    )
    assert subtitle_segments(vtt)[0].text == "Hola mundo"


def test_mm_ss_timing_and_cue_settings() -> None:
    vtt = "WEBVTT\n\n01:05.500 --> 01:09.000 align:start position:0%\nhola\n"
    segment = subtitle_segments(vtt)[0]
    assert segment.start_ms == 65_500
    assert segment.end_ms == 69_000


def test_note_style_region_blocks_are_skipped() -> None:
    vtt = (
        "WEBVTT\n\n"
        "NOTE esto es una nota\nlinea de nota\n\n"
        "STYLE\n::cue { color: red }\n\n"
        "REGION\nid:r1\n\n"
        "00:00:00.000 --> 00:00:01.000\nhola\n"
    )
    segments = subtitle_segments(vtt)
    assert len(segments) == 1
    assert segments[0].text == "hola"


# --------------------------------------------------------------------------- #
# Formato canónico (seed y tests)
# --------------------------------------------------------------------------- #


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
