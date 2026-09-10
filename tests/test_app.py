from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from radar import db
from radar.app import create_app
from radar.config import get_settings
from radar.models import Chunk, VideoMeta


class FakeAI:
    def __init__(self, settings=None):
        self.settings = settings

    def resolve_embedding(self) -> str:
        return "m"

    def resolve_chat(self) -> str:
        return "m"

    def embed(self, texts, model):
        return [[1.0, 0.0, 0.0] for _ in texts]

    def chat(self, system, user, model):
        return "Respuesta con cita [1]."


def build_client(tmp_path, monkeypatch, *, seeded: bool, recent: bool = False):
    monkeypatch.setattr("radar.app.AIClient", FakeAI)
    settings = replace(get_settings(load_dotenv=False), db_path=tmp_path / "radar.db")
    if seeded:
        conn = db.connect(settings.db_path)
        db.init_db(conn)
        published = (
            datetime.now(timezone.utc).isoformat(timespec="seconds")
            if recent
            else "2025-01-01T00:00:00Z"
        )
        db.upsert_video(
            conn,
            VideoMeta(video_id="v1", title="Charla", lang="es", published_at=published),
            None,
        )
        db.insert_chunks(conn, [Chunk("v1", 0, 60_000, "inteligencia artificial en español")])
        chunk_id = conn.execute("SELECT id FROM chunks").fetchone()["id"]
        import numpy as np

        db.save_embedding(
            conn, chunk_id, np.array([1, 0, 0], dtype=np.float32).tobytes(), "m", 3
        )
        conn.commit()
        conn.close()
    return TestClient(create_app(settings))


def test_health(tmp_path, monkeypatch):
    client = build_client(tmp_path, monkeypatch, seeded=False)
    assert client.get("/api/health").json()["ok"] is True


def test_empty_db_shows_notice(tmp_path, monkeypatch):
    client = build_client(tmp_path, monkeypatch, seeded=False)
    stats = client.get("/api/stats").json()
    assert stats["empty"] is True
    assert "make seed" in stats["notice"]
    response = client.get("/api/search", params={"q": "hola"}).json()
    assert response["empty"] is True
    assert response["results"] == []


def test_search_returns_results_and_answer(tmp_path, monkeypatch):
    client = build_client(tmp_path, monkeypatch, seeded=True)
    body = client.get("/api/search", params={"q": "inteligencia"}).json()
    assert body["results"]
    assert body["results"][0]["video_id"] == "v1"
    assert body["results"][0]["start_label"] == "0:00"
    assert body["answer"] == "Respuesta con cita [1]."


def test_week_returns_topics_when_recent(tmp_path, monkeypatch):
    client = build_client(tmp_path, monkeypatch, seeded=True, recent=True)
    body = client.get("/api/week", params={"days": 7}).json()
    assert body["topics"]
    assert body["topics"][0]["count"] >= 1
