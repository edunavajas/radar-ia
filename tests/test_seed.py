from __future__ import annotations

from radar import db, ingest
from radar.models import Chunk, Segment, VideoMeta
from radar.seed import export_seed


def _seed_conn():
    conn = db.connect(":memory:")
    db.init_db(conn)
    data = [
        ("@es", "es", "v-es", "2025-01-03"),
        ("@en", "en", "v-en", "2025-01-02"),
        ("@ja", "ja", "v-ja", "2025-01-01"),
    ]
    for handle, lang, video_id, published in data:
        db.upsert_channel(conn, handle, f"https://youtube.com/{handle}/videos", handle, lang)
        db.upsert_video(
            conn,
            VideoMeta(video_id=video_id, channel_handle=handle, lang=lang, published_at=published),
            db.channel_id_for(conn, handle),
        )
        db.save_transcript(conn, video_id, lang, "auto_generated", [Segment(0, 1000, "texto")])
    conn.commit()
    return conn


def test_export_seed_roundtrip(tmp_path) -> None:
    conn = _seed_conn()
    path = tmp_path / "seed.jsonl"
    count = export_seed(conn, path, target=3)
    assert count == 3
    text = path.read_text(encoding="utf-8")
    assert '"type": "channel"' in text
    assert '"type": "video"' in text
    assert '"type": "transcript"' in text

    fresh = db.connect(":memory:")
    db.init_db(fresh)
    summary = ingest.ingest_seed(fresh, path, ingest.Summary())
    assert summary.new_videos == 3
    assert summary.new_transcripts == 3
    assert db.stats(fresh)["videos"] == 3


def test_export_seed_includes_asian_language(tmp_path) -> None:
    conn = _seed_conn()
    path = tmp_path / "seed.jsonl"
    export_seed(conn, path, target=1)
    assert "ja" in path.read_text(encoding="utf-8")


def test_export_seed_without_transcripts(tmp_path) -> None:
    conn = db.connect(":memory:")
    db.init_db(conn)
    assert export_seed(conn, tmp_path / "seed.jsonl", target=5) == 0
