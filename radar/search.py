"""Búsqueda híbrida: BM25 de FTS5 + coseno con numpy, fusionados con RRF.

Con unos pocos miles de chunks, cargar los vectores en memoria y calcular cosenos
con numpy va sobrado: no hace falta una base vectorial.
"""

from __future__ import annotations

import re
import sqlite3

import numpy as np

from . import db

RRF_K = 60
CANDIDATES = 200


def _fts_ids(conn: sqlite3.Connection, query: str, candidates: set[int] | None) -> list[int]:
    terms = [t for t in re.split(r"\s+", query.strip()) if t]
    if not terms:
        return []
    match = " OR ".join('"' + t.replace('"', '""') + '"' for t in terms)
    try:
        rows = conn.execute(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? "
            "ORDER BY bm25(chunks_fts) LIMIT ?",
            (match, CANDIDATES),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [r["rowid"] for r in rows if candidates is None or r["rowid"] in candidates]


def _cosine_ids(
    conn: sqlite3.Connection,
    query_vec: list[float],
    model: str,
    candidates: set[int] | None,
    limit: int = CANDIDATES,
) -> list[int]:
    rows = db.all_embeddings(conn, model)
    ids: list[int] = []
    vectors: list[np.ndarray] = []
    for row in rows:
        if candidates is not None and row["chunk_id"] not in candidates:
            continue
        ids.append(int(row["chunk_id"]))
        vectors.append(np.frombuffer(row["vector"], dtype=np.float32))
    if not ids:
        return []
    matrix = np.vstack(vectors)
    matrix = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
    query = np.asarray(query_vec, dtype=np.float32)
    query = query / (np.linalg.norm(query) + 1e-9)
    order = np.argsort(-(matrix @ query))[:limit]
    return [ids[i] for i in order]


def rrf(rankings: list[list[int]], k: int = RRF_K) -> list[int]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)
    return [cid for cid, _ in sorted(scores.items(), key=lambda kv: -kv[1])]


def _candidate_ids(conn: sqlite3.Connection, filters: dict) -> set[int] | None:
    clauses: list[str] = []
    params: list = []
    if filters.get("lang"):
        clauses.append("v.lang = ?")
        params.append(filters["lang"])
    if filters.get("channel"):
        clauses.append("ch.name LIKE ?")
        params.append(f"%{filters['channel']}%")
    if filters.get("published_after"):
        clauses.append("v.published_at >= ?")
        params.append(filters["published_after"])
    if not clauses:
        return None
    rows = conn.execute(
        "SELECT c.id FROM chunks c "
        "JOIN videos v ON v.video_id = c.video_id "
        "LEFT JOIN channels ch ON ch.id = v.channel_id "
        f"WHERE {' AND '.join(clauses)}",
        params,
    ).fetchall()
    return {int(r["id"]) for r in rows}


def start_label(start_ms: int) -> str:
    total = start_ms // 1000
    return f"{total // 60}:{total % 60:02d}"


def hydrate(conn: sqlite3.Connection, ids: list[int]) -> list[dict]:
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT c.id, c.video_id, c.start_ms, c.end_ms, c.text,
               v.title, v.published_at, v.lang, v.thumbnail_url, v.duration_s,
               ch.name AS channel_name, ch.handle AS channel_handle
        FROM chunks c
        JOIN videos v ON v.video_id = c.video_id
        LEFT JOIN channels ch ON ch.id = v.channel_id
        WHERE c.id IN ({placeholders})
        """,
        tuple(ids),
    ).fetchall()
    by_id = {int(r["id"]): r for r in rows}
    results = []
    for rank, chunk_id in enumerate(ids, start=1):
        r = by_id.get(chunk_id)
        if r is None:
            continue
        results.append(
            {
                "rank": rank,
                "chunk_id": chunk_id,
                "video_id": r["video_id"],
                "title": r["title"] or "",
                "channel": r["channel_name"] or r["channel_handle"] or "",
                "published_at": r["published_at"] or "",
                "lang": r["lang"] or "",
                "thumbnail_url": r["thumbnail_url"] or "",
                "start_ms": r["start_ms"],
                "end_ms": r["end_ms"],
                "start_label": start_label(r["start_ms"]),
                "watch_url": f"https://www.youtube.com/watch?v={r['video_id']}&t={r['start_ms'] // 1000}s",
                "text": r["text"],
            }
        )
    return results


def hybrid_search(
    conn: sqlite3.Connection,
    ai,
    question: str,
    model: str,
    top_k: int = 8,
    filters: dict | None = None,
) -> list[dict]:
    filters = filters or {}
    candidates = _candidate_ids(conn, filters)
    if candidates is not None and not candidates:
        return []
    fts_ids = _fts_ids(conn, question, candidates)
    query_vec = ai.embed([question], model)[0]
    vector_ids = _cosine_ids(conn, query_vec, model, candidates)
    fused = rrf([fts_ids, vector_ids])[:top_k]
    return hydrate(conn, fused)


def keyword_search(
    conn: sqlite3.Connection,
    question: str,
    top_k: int = 8,
    filters: dict | None = None,
) -> list[dict]:
    """Búsqueda solo BM25, para cuando el proveedor de IA no está disponible."""
    filters = filters or {}
    candidates = _candidate_ids(conn, filters)
    if candidates is not None and not candidates:
        return []
    return hydrate(conn, _fts_ids(conn, question, candidates)[:top_k])
