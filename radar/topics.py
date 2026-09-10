"""Temas más repetidos de los últimos N días, por frecuencia de términos.

Agrupación ligera y determinista (sin LLM): basta para la vista "Esta semana".
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from . import db

_WORD = re.compile(r"[a-zà-ÿ0-9]{4,}")

_STOPWORDS = {
    # es
    "para", "pero", "como", "este", "esta", "esto", "estos", "estas", "porque",
    "cuando", "donde", "desde", "hasta", "sobre", "entre", "también", "tambien",
    "muy", "más", "mas", "los", "las", "una", "unos", "unas", "del", "que",
    "con", "por", "sus", "sea", "son", "fue", "ser", "han", "hay", "tiene",
    # en
    "that", "this", "with", "have", "from", "they", "will", "your", "what",
    "when", "which", "there", "their", "about", "would", "could", "should",
    "into", "than", "then", "them", "these", "those", "been", "were", "here",
    # de / fr / pt
    "nicht", "eine", "einen", "auch", "aber", "oder", "wird", "werden", "dans",
    "pour", "avec", "plus", "nous", "vous", "mais", "para", "como", "ser",
}


def week_topics(conn, days: int = 7, limit: int = 8) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    rows = conn.execute(
        """
        SELECT c.id, c.text, c.video_id, c.start_ms, c.end_ms,
               v.title, v.lang, v.published_at, v.thumbnail_url,
               ch.name AS channel_name
        FROM chunks c
        JOIN videos v ON v.video_id = c.video_id
        LEFT JOIN channels ch ON ch.id = v.channel_id
        WHERE v.published_at >= ?
        """,
        (since,),
    ).fetchall()
    if not rows:
        return []

    counts: Counter[str] = Counter()
    by_term: dict[str, list] = {}
    for row in rows:
        seen = set()
        for term in _WORD.findall((row["text"] or "").lower()):
            if term in _STOPWORDS or term in seen:
                continue
            seen.add(term)
            counts[term] += 1
            by_term.setdefault(term, []).append(row)

    topics = []
    for term, count in counts.most_common(limit):
        samples = by_term[term][:3]
        topics.append(
            {
                "term": term,
                "count": count,
                "samples": [
                    {
                        "video_id": r["video_id"],
                        "title": r["title"] or "",
                        "channel": r["channel_name"] or "",
                        "lang": r["lang"] or "",
                        "thumbnail_url": r["thumbnail_url"] or "",
                        "start_ms": r["start_ms"],
                        "start_label": f"{(r['start_ms'] // 1000) // 60}:{(r['start_ms'] // 1000) % 60:02d}",
                        "watch_url": f"https://www.youtube.com/watch?v={r['video_id']}&t={r['start_ms'] // 1000}s",
                        "text": r["text"],
                    }
                    for r in samples
                ],
            }
        )
    return topics
