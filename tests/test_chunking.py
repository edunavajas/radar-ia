from __future__ import annotations

from radar.chunking import (
    OVERLAP_MS,
    TARGET_MAX_MS,
    TARGET_MIN_MS,
    chunk_segments,
    estimate_tokens,
)
from radar.models import Segment


def make_segments(count: int, step_ms: int = 5_000) -> list[Segment]:
    return [
        Segment(start_ms=i * step_ms, end_ms=(i + 1) * step_ms, text=f"frase {i}")
        for i in range(count)
    ]


def test_chunks_within_target_range() -> None:
    chunks = chunk_segments("vid", make_segments(48))  # 4 minutos
    assert chunks
    for c in chunks[:-1]:
        assert TARGET_MIN_MS <= c.end_ms - c.start_ms <= TARGET_MAX_MS


def test_first_chunk_starts_at_zero_and_conserves_text() -> None:
    chunks = chunk_segments("vid", make_segments(24))
    assert chunks[0].start_ms == 0
    assert "frase 0" in chunks[0].text
    assert chunks[0].video_id == "vid"


def test_consecutive_chunks_overlap() -> None:
    chunks = chunk_segments("vid", make_segments(48))
    assert len(chunks) >= 2
    for prev, nxt in zip(chunks, chunks[1:]):
        # El siguiente empieza antes de que acabe el anterior, pero no antes
        # de lo que marca el solape.
        assert nxt.start_ms < prev.end_ms
        assert nxt.start_ms >= prev.end_ms - OVERLAP_MS


def test_blank_segments_are_ignored() -> None:
    segs = make_segments(18)
    segs.insert(0, Segment(start_ms=0, end_ms=100, text="   "))
    chunks = chunk_segments("vid", segs)
    assert chunks[0].start_ms == 0
    assert chunks[0].text.startswith("frase 0")


def test_single_segment_longer_than_max_is_emitted_alone() -> None:
    segs = [
        Segment(start_ms=0, end_ms=200_000, text="un monólogo muy largo"),
        Segment(start_ms=200_000, end_ms=205_000, text="y sigue"),
    ]
    chunks = chunk_segments("vid", segs)
    assert chunks[0].end_ms - chunks[0].start_ms >= TARGET_MAX_MS
    assert chunks[0].text.startswith("un monólogo")
    assert len(chunks) >= 2


def test_empty_input() -> None:
    assert chunk_segments("vid", []) == []


def test_estimate_tokens_handles_cjk() -> None:
    assert estimate_tokens("你好世界") == 4
    assert estimate_tokens("") == 1
