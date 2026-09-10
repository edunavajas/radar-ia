from __future__ import annotations

import json

from radar import db, ingest


def write_seed(tmp_path):
    lines = [
        {"type": "channel", "handle": "@x", "url": "https://youtube.com/@x/videos", "name": "X", "lang": "en"},
        {
            "type": "video",
            "video_id": "v1",
            "channel_handle": "@x",
            "title": "Charla",
            "published_at": "2025-01-01T00:00:00Z",
        },
        {
            "type": "transcript",
            "video_id": "v1",
            "lang": "en",
            "subtitle_type": "auto_generated",
            "segments": [{"start_ms": 0, "end_ms": 1000, "text": "hello world"}],
        },
    ]
    path = tmp_path / "seed.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")
    return path


def test_seed_loads_and_is_idempotent(tmp_path) -> None:
    conn = db.connect(":memory:")
    db.init_db(conn)
    seed = write_seed(tmp_path)

    first = ingest.ingest_seed(conn, seed, ingest.Summary())
    assert first.new_videos == 1
    assert first.new_transcripts == 1

    second = ingest.ingest_seed(conn, seed, ingest.Summary())
    assert second.new_videos == 0
    assert second.skipped == 1
    assert db.stats(conn)["videos"] == 1


def test_from_samples_without_files_is_a_note_not_a_crash(tmp_path) -> None:
    conn = db.connect(":memory:")
    db.init_db(conn)
    summary = ingest.ingest_from_samples(conn, tmp_path, ingest.Summary())
    assert any("No hay ficheros" in n for n in summary.notes)


def test_live_reports_credits_without_stacktrace(monkeypatch) -> None:
    from radar.config import get_settings
    from radar.thordata import CreditsExhausted

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

        def launch(self, request):
            raise CreditsExhausted("La cuenta no tiene créditos de scraper.")

    monkeypatch.setattr(ingest, "ThordataClient", FakeClient)
    conn = db.connect(":memory:")
    db.init_db(conn)
    summary = ingest.ingest_live(
        conn,
        get_settings(load_dotenv=False),
        {"channels": [{"url": "https://youtube.com/@x/videos", "max_posts": 1}]},
        ingest.Summary(),
        assume_yes=True,
    )
    assert any("créditos" in n for n in summary.notes)

