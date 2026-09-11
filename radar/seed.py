"""Exporta un `seed/seed.jsonl` canónico desde lo ya ingerido.

Selecciona vídeos con transcripción buscando una mezcla de idiomas y, si hay,
al menos uno asiático (zh/ja/ko). El formato es el que entiende `ingest_seed`.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import db

ASIAN_LANGS = {"zh", "zh-Hans", "zh-Hant", "zh-CN", "zh-TW", "ja", "ko"}

QUERY = """
SELECT v.video_id, v.title, v.description, v.published_at, v.duration_s,
       v.view_count, v.like_count, v.lang, v.url, v.thumbnail_url,
       ch.handle AS ch_handle, ch.url AS ch_url, ch.name AS ch_name,
       ch.lang AS ch_lang, ch.channel_id AS ch_id
FROM videos v
JOIN transcripts t ON t.video_id = v.video_id
LEFT JOIN channels ch ON ch.id = v.channel_id
ORDER BY COALESCE(v.published_at, '') DESC
"""


def _select(rows, target: int) -> list:
    by_lang: dict[str, list] = {}
    for row in rows:
        by_lang.setdefault(row["lang"] or "??", []).append(row)
    langs = sorted(by_lang, key=lambda lang: (-len(by_lang[lang]), lang))

    selected: list = []
    while len(selected) < target:
        progressed = False
        for lang in langs:
            if by_lang[lang] and len(selected) < target:
                selected.append(by_lang[lang].pop(0))
                progressed = True
        if not progressed:
            break

    if selected and not any((row["lang"] or "") in ASIAN_LANGS for row in selected):
        for lang in langs:
            if lang in ASIAN_LANGS and by_lang.get(lang):
                selected[-1] = by_lang[lang].pop(0)
                break
    return selected


def export_seed(conn, path: Path | str, target: int = 18) -> int:
    rows = conn.execute(QUERY).fetchall()
    if not rows:
        return 0
    selected = _select(rows, target)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    seen_channels = set()
    for row in selected:
        handle = row["ch_handle"] or ""
        if handle and handle not in seen_channels:
            seen_channels.add(handle)
            lines.append(
                json.dumps(
                    {
                        "type": "channel",
                        "handle": handle,
                        "url": row["ch_url"] or "",
                        "name": row["ch_name"] or "",
                        "lang": row["ch_lang"] or "",
                        "channel_id": row["ch_id"] or "",
                    },
                    ensure_ascii=False,
                )
            )
    for row in selected:
        lines.append(
            json.dumps(
                {
                    "type": "video",
                    "video_id": row["video_id"],
                    "channel_handle": row["ch_handle"] or "",
                    "channel_id": row["ch_id"] or "",
                    "title": row["title"] or "",
                    "description": row["description"] or "",
                    "published_at": row["published_at"] or "",
                    "duration_s": row["duration_s"],
                    "view_count": row["view_count"],
                    "like_count": row["like_count"],
                    "lang": row["lang"] or "",
                    "url": row["url"] or "",
                    "thumbnail_url": row["thumbnail_url"] or "",
                },
                ensure_ascii=False,
            )
        )
    for row in selected:
        segments = [
            {"start_ms": seg.start_ms, "end_ms": seg.end_ms, "text": seg.text}
            for seg in db.segments_for(conn, row["video_id"])
        ]
        lines.append(
            json.dumps(
                {
                    "type": "transcript",
                    "video_id": row["video_id"],
                    "lang": row["lang"] or "",
                    "subtitle_type": "auto_generated",
                    "segments": segments,
                },
                ensure_ascii=False,
            )
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(selected)
