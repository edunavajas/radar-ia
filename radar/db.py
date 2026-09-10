"""SQLite + FTS5: esquema y utilidades de acceso a datos.

Un único sitio para el esquema. Las claves de deduplicación son `videos.video_id`
y `embeddings.chunk_id` (un vector por trozo y modelo vigente).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS channels(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  handle TEXT UNIQUE,
  url TEXT,
  name TEXT,
  lang TEXT
);

CREATE TABLE IF NOT EXISTS videos(
  video_id TEXT PRIMARY KEY,
  channel_id INTEGER REFERENCES channels(id),
  title TEXT,
  description TEXT,
  published_at TEXT,
  duration_s INTEGER,
  view_count INTEGER,
  lang TEXT,
  url TEXT,
  thumbnail_url TEXT,
  fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS transcripts(
  video_id TEXT NOT NULL REFERENCES videos(video_id),
  lang TEXT NOT NULL,
  subtitle_type TEXT NOT NULL,
  raw_path TEXT,
  fetched_at TEXT,
  PRIMARY KEY(video_id, lang, subtitle_type)
);

CREATE TABLE IF NOT EXISTS segments(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id TEXT NOT NULL REFERENCES videos(video_id),
  start_ms INTEGER NOT NULL,
  end_ms INTEGER NOT NULL,
  text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_segments_video ON segments(video_id, start_ms);

CREATE TABLE IF NOT EXISTS chunks(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id TEXT NOT NULL REFERENCES videos(video_id),
  start_ms INTEGER NOT NULL,
  end_ms INTEGER NOT NULL,
  text TEXT NOT NULL,
  token_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_chunks_video ON chunks(video_id, start_ms);

CREATE TABLE IF NOT EXISTS embeddings(
  chunk_id INTEGER PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
  vector BLOB NOT NULL,
  model TEXT NOT NULL,
  dim INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS api_calls(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider TEXT NOT NULL,
  spider_id TEXT,
  params_hash TEXT,
  status TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: Path | str) -> sqlite3.Connection:
    db_path = Path(db_path)
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def is_empty(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0] == 0


# --------------------------------------------------------------------------- #
# Escritura
# --------------------------------------------------------------------------- #


def upsert_channel(conn: sqlite3.Connection, handle: str, url: str, name: str, lang: str) -> int:
    conn.execute(
        """
        INSERT INTO channels(handle, url, name, lang) VALUES(?,?,?,?)
        ON CONFLICT(handle) DO UPDATE SET
          url=COALESCE(NULLIF(excluded.url,''), channels.url),
          name=COALESCE(NULLIF(excluded.name,''), channels.name),
          lang=COALESCE(NULLIF(excluded.lang,''), channels.lang)
        """,
        (handle, url, name, lang),
    )
    row = conn.execute("SELECT id FROM channels WHERE handle=?", (handle,)).fetchone()
    return int(row["id"])


def channel_id_for(conn: sqlite3.Connection, handle: str) -> int | None:
    if not handle:
        return None
    row = conn.execute("SELECT id FROM channels WHERE handle=?", (handle,)).fetchone()
    return int(row["id"]) if row else None


def upsert_video(conn: sqlite3.Connection, video, channel_id: int | None) -> None:
    conn.execute(
        """
        INSERT INTO videos(video_id, channel_id, title, description, published_at,
                           duration_s, view_count, lang, url, thumbnail_url, fetched_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(video_id) DO UPDATE SET
          channel_id=COALESCE(excluded.channel_id, videos.channel_id),
          title=COALESCE(NULLIF(excluded.title,''), videos.title),
          description=COALESCE(NULLIF(excluded.description,''), videos.description),
          published_at=COALESCE(NULLIF(excluded.published_at,''), videos.published_at),
          duration_s=CASE WHEN excluded.duration_s>0 THEN excluded.duration_s ELSE videos.duration_s END,
          view_count=CASE WHEN excluded.view_count>0 THEN excluded.view_count ELSE videos.view_count END,
          lang=COALESCE(NULLIF(excluded.lang,''), videos.lang),
          url=COALESCE(NULLIF(excluded.url,''), videos.url),
          thumbnail_url=COALESCE(NULLIF(excluded.thumbnail_url,''), videos.thumbnail_url)
        """,
        (
            video.video_id,
            channel_id,
            video.title,
            video.description,
            video.published_at,
            video.duration_s,
            video.view_count,
            video.lang,
            video.url,
            video.thumbnail_url,
            now_iso(),
        ),
    )


def video_exists(conn: sqlite3.Connection, video_id: str) -> bool:
    return (
        conn.execute("SELECT 1 FROM videos WHERE video_id=?", (video_id,)).fetchone()
        is not None
    )


def has_transcript(conn: sqlite3.Connection, video_id: str, lang: str, subtitle_type: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM transcripts WHERE video_id=? AND lang=? AND subtitle_type=?",
            (video_id, lang, subtitle_type),
        ).fetchone()
        is not None
    )


def save_transcript(
    conn: sqlite3.Connection,
    video_id: str,
    lang: str,
    subtitle_type: str,
    segments,
    raw_path: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO transcripts(video_id, lang, subtitle_type, raw_path, fetched_at)
        VALUES(?,?,?,?,?)
        ON CONFLICT(video_id, lang, subtitle_type) DO UPDATE SET
          raw_path=COALESCE(NULLIF(excluded.raw_path,''), transcripts.raw_path),
          fetched_at=excluded.fetched_at
        """,
        (video_id, lang, subtitle_type, raw_path, now_iso()),
    )
    conn.execute("DELETE FROM segments WHERE video_id=?", (video_id,))
    conn.executemany(
        "INSERT INTO segments(video_id, start_ms, end_ms, text) VALUES(?,?,?,?)",
        [(video_id, s.start_ms, s.end_ms, s.text) for s in segments],
    )


def segments_for(conn: sqlite3.Connection, video_id: str):
    from .models import Segment

    rows = conn.execute(
        "SELECT start_ms, end_ms, text FROM segments WHERE video_id=? ORDER BY start_ms",
        (video_id,),
    ).fetchall()
    return [Segment(r["start_ms"], r["end_ms"], r["text"]) for r in rows]


def delete_chunks(conn: sqlite3.Connection, video_id: str) -> None:
    rows = conn.execute("SELECT id FROM chunks WHERE video_id=?", (video_id,)).fetchall()
    for r in rows:
        conn.execute("DELETE FROM chunks_fts WHERE rowid=?", (r["id"],))
    conn.execute("DELETE FROM chunks WHERE video_id=?", (video_id,))


def insert_chunks(conn: sqlite3.Connection, chunks) -> int:
    first_id = None
    for c in chunks:
        cur = conn.execute(
            "INSERT INTO chunks(video_id, start_ms, end_ms, text, token_count) VALUES(?,?,?,?,?)",
            (c.video_id, c.start_ms, c.end_ms, c.text, c.token_count),
        )
        cid = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO chunks_fts(rowid, text) VALUES(?,?)", (cid, c.text)
        )
        if first_id is None:
            first_id = cid
    return len(chunks)


def chunks_without_embedding(conn: sqlite3.Connection, model: str):
    return conn.execute(
        """
        SELECT c.id, c.text FROM chunks c
        LEFT JOIN embeddings e ON e.chunk_id = c.id AND e.model = ?
        WHERE e.chunk_id IS NULL
        ORDER BY c.id
        """,
        (model,),
    ).fetchall()


def save_embedding(conn: sqlite3.Connection, chunk_id: int, vector: bytes, model: str, dim: int) -> None:
    conn.execute(
        """
        INSERT INTO embeddings(chunk_id, vector, model, dim) VALUES(?,?,?,?)
        ON CONFLICT(chunk_id) DO UPDATE SET vector=excluded.vector, model=excluded.model, dim=excluded.dim
        """,
        (chunk_id, vector, model, dim),
    )


def all_embeddings(conn: sqlite3.Connection, model: str):
    return conn.execute(
        "SELECT chunk_id, vector, dim FROM embeddings WHERE model=?", (model,)
    ).fetchall()


def record_api_call(
    conn: sqlite3.Connection, provider: str, spider_id: str, params: dict | None, status: str
) -> None:
    params_hash = hashlib.sha256(
        json.dumps(params or {}, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]
    conn.execute(
        "INSERT INTO api_calls(provider, spider_id, params_hash, status, created_at) VALUES(?,?,?,?,?)",
        (provider, spider_id, params_hash, status, now_iso()),
    )


def api_call_count(conn: sqlite3.Connection, provider: str | None = None) -> int:
    if provider:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM api_calls WHERE provider=?", (provider,)
            ).fetchone()[0]
        )
    return int(conn.execute("SELECT COUNT(*) FROM api_calls").fetchone()[0])


def meta_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def stats(conn: sqlite3.Connection) -> dict:
    q = lambda sql: int(conn.execute(sql).fetchone()[0])
    return {
        "channels": q("SELECT COUNT(*) FROM channels"),
        "videos": q("SELECT COUNT(*) FROM videos"),
        "transcripts": q("SELECT COUNT(*) FROM transcripts"),
        "segments": q("SELECT COUNT(*) FROM segments"),
        "chunks": q("SELECT COUNT(*) FROM chunks"),
        "embeddings": q("SELECT COUNT(*) FROM embeddings"),
        "empty": is_empty(conn),
    }
