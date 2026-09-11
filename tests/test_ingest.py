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
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from radar.config import get_settings
    from radar.sources import VideoRef
    from radar.thordata import CreditsExhausted

    class FakeDiscovery:
        def resolve_channel_id(self, target):
            return "UC" + "x" * 22

        def discover(self, channel):
            return [
                VideoRef(
                    video_id="v1",
                    title="t",
                    published_at=datetime.now(timezone.utc).isoformat(),
                )
            ]

        def close(self):
            pass

    class FakeMetadata:
        def fetch(self, video_id):
            from radar.models import VideoMeta

            return VideoMeta(video_id=video_id, title="t")

        def close(self):
            pass

    class FakeTranscript:
        def fetch(self, video_id, lang=None):
            raise CreditsExhausted("La cuenta no tiene créditos de scraper.")

    class FakeClient:
        def close(self):
            pass

    monkeypatch.setattr(ingest, "discovery_source", lambda settings: FakeDiscovery())
    monkeypatch.setattr(ingest, "metadata_source", lambda settings: FakeMetadata())
    monkeypatch.setattr(ingest, "transcript_source", lambda settings, client=None: FakeTranscript())
    monkeypatch.setattr(ingest, "ThordataClient", lambda settings: FakeClient())

    conn = db.connect(":memory:")
    db.init_db(conn)
    args = SimpleNamespace(
        days=7, limit=10, dry_run=False, yes=True, workers=1, write_seed="", seed_count=0
    )
    summary = ingest.ingest_live(
        conn,
        get_settings(load_dotenv=False),
        {"channels": [{"channel_id": "UC" + "x" * 22, "lang": "en"}]},
        ingest.Summary(),
        args,
    )
    assert any("créditos" in n for n in summary.notes)

