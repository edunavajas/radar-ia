from __future__ import annotations

import numpy as np

from radar import db
from radar.answer import build_prompt, synthesize
from radar.models import Chunk, VideoMeta
from radar.search import hybrid_search, rrf, start_label


class FakeAI:
    """Embeddings deterministas: devuelve un vector fijo por texto."""

    def __init__(self, mapping: dict[str, list[float]]):
        self.mapping = mapping

    def embed(self, texts, model):
        return [self.mapping[t] for t in texts]


def seeded_conn():
    conn = db.connect(":memory:")
    db.init_db(conn)
    db.upsert_video(
        conn,
        VideoMeta(video_id="v1", title="Charla IA", lang="es", published_at="2025-01-10"),
        None,
    )
    db.upsert_video(
        conn,
        VideoMeta(video_id="v2", title="AI talk", lang="en", published_at="2025-01-01"),
        None,
    )
    db.insert_chunks(conn, [Chunk("v1", 0, 60_000, "inteligencia artificial en español")])
    db.insert_chunks(conn, [Chunk("v2", 0, 60_000, "artificial intelligence in english")])
    rows = conn.execute("SELECT id, video_id FROM chunks ORDER BY id").fetchall()
    ids = {r["video_id"]: r["id"] for r in rows}
    db.save_embedding(conn, ids["v1"], np.array([1, 0, 0], dtype=np.float32).tobytes(), "m", 3)
    db.save_embedding(conn, ids["v2"], np.array([0, 1, 0], dtype=np.float32).tobytes(), "m", 3)
    return conn


def test_rrf_fuses_and_orders() -> None:
    assert rrf([[1, 2], [2, 1]])[0] == 1
    assert set(rrf([[1], [2]])) == {1, 2}


def test_hybrid_search_prefers_semantic_match() -> None:
    conn = seeded_conn()
    ai = FakeAI({"inteligencia": [1, 0, 0]})
    results = hybrid_search(conn, ai, "inteligencia", "m", top_k=5)
    assert results
    assert results[0]["video_id"] == "v1"
    assert results[0]["watch_url"].endswith("&t=0s")
    assert results[0]["start_label"] == "0:00"


def test_hybrid_search_respects_lang_filter() -> None:
    conn = seeded_conn()
    ai = FakeAI({"inteligencia": [1, 0, 0]})
    results = hybrid_search(conn, ai, "inteligencia", "m", filters={"lang": "en"})
    assert [r["video_id"] for r in results] == ["v2"]


def test_filter_with_no_matches_returns_empty() -> None:
    conn = seeded_conn()
    ai = FakeAI({"inteligencia": [1, 0, 0]})
    assert hybrid_search(conn, ai, "inteligencia", "m", filters={"lang": "zh"}) == []


def test_start_label_formats_minutes() -> None:
    assert start_label(754_000) == "12:34"


def test_synthesize_falls_back_when_chat_fails() -> None:
    class BrokenAI:
        def chat(self, *args, **kwargs):
            raise RuntimeError("boom")

    results = [{"video_id": "v1", "start_label": "0:10", "title": "t", "lang": "es", "text": "x"}]
    assert synthesize("p", results, BrokenAI(), "m") is None


def test_synthesize_returns_text_and_prompt_has_citations() -> None:
    class EchoAI:
        def chat(self, system, user, model):
            assert "[1]" in user
            return "Respuesta [1]"

    results = [{"video_id": "v1", "start_label": "0:10", "title": "t", "lang": "es", "text": "x"}]
    assert synthesize("p", results, EchoAI(), "m") == "Respuesta [1]"
    assert "[1]" in build_prompt("p", results)
