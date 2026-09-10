from __future__ import annotations

import numpy as np
import pytest

from radar import db
from radar.models import Chunk, Segment, VideoMeta


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


def test_video_dedup(conn) -> None:
    assert db.video_exists(conn, "a") is False
    db.upsert_video(conn, VideoMeta(video_id="a", title="t"), None)
    assert db.video_exists(conn, "a") is True


def test_stats_reports_empty(conn) -> None:
    assert db.stats(conn)["empty"] is True
    db.upsert_video(conn, VideoMeta(video_id="a"), None)
    assert db.stats(conn)["empty"] is False


def test_transcript_and_segments_roundtrip(conn) -> None:
    db.upsert_video(conn, VideoMeta(video_id="a"), None)
    db.save_transcript(conn, "a", "en", "auto_generated", [Segment(0, 1000, "hola")])
    segs = db.segments_for(conn, "a")
    assert [s.text for s in segs] == ["hola"]
    assert db.has_transcript(conn, "a", "en", "auto_generated") is True


def test_chunks_indexed_in_fts(conn) -> None:
    db.upsert_video(conn, VideoMeta(video_id="a"), None)
    db.insert_chunks(conn, [Chunk("a", 0, 60_000, "inteligencia artificial aplicada")])
    rows = conn.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?", ("inteligencia",)
    ).fetchall()
    assert rows
    chunk_id = rows[0]["rowid"]
    assert conn.execute("SELECT text FROM chunks WHERE id=?", (chunk_id,)).fetchone() is not None


def test_api_call_counting(conn) -> None:
    db.record_api_call(conn, "thordata", "youtube_transcript_by-id", {"video_id": "a"}, "ok")
    db.record_api_call(conn, "ai", "embeddings", {"n": 3}, "ok")
    assert db.api_call_count(conn) == 2
    assert db.api_call_count(conn, "thordata") == 1
    assert db.api_call_count(conn, "ai") == 1


def test_embedding_roundtrip(conn) -> None:
    db.upsert_video(conn, VideoMeta(video_id="a"), None)
    db.insert_chunks(conn, [Chunk("a", 0, 60_000, "texto")])
    chunk_id = conn.execute("SELECT id FROM chunks").fetchone()["id"]
    vec = np.array([0.5, 0.25, 0.125], dtype=np.float32)
    db.save_embedding(conn, chunk_id, vec.tobytes(), "qwen3-embedding", 3)
    row = db.all_embeddings(conn, "qwen3-embedding")[0]
    assert np.frombuffer(row["vector"], dtype=np.float32).tolist() == [0.5, 0.25, 0.125]
    assert db.chunks_without_embedding(conn, "qwen3-embedding") == []


def test_meta_roundtrip(conn) -> None:
    assert db.meta_get(conn, "embedding_dim") is None
    db.meta_set(conn, "embedding_dim", 4096)
    assert db.meta_get(conn, "embedding_dim") == "4096"
