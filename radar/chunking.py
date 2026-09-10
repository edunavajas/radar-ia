"""Troceado de segmentos de subtítulos.

Agrupa segmentos en trozos de 60–90 s con 15 s de solape, conservando el
`start_ms` del primer segmento de cada trozo. Si un segmento aislado ya supera
el máximo, se emite solo para no perder contenido.
"""

from __future__ import annotations

from .models import Chunk, Segment

TARGET_MIN_MS = 60_000
TARGET_MAX_MS = 90_000
OVERLAP_MS = 15_000


def estimate_tokens(text: str) -> int:
    """Estimación barata y determinista, válida para texto latino y CJK."""
    cjk = sum(
        1
        for c in text
        if "\u4e00" <= c <= "\u9fff"  # han
        or "\u3040" <= c <= "\u30ff"  # kana
        or "\uac00" <= c <= "\ud7af"  # hangul
    )
    return max(1, cjk + (len(text) - cjk) // 4)


def chunk_segments(
    video_id: str,
    segments: list[Segment],
    target_min_ms: int = TARGET_MIN_MS,
    target_max_ms: int = TARGET_MAX_MS,
    overlap_ms: int = OVERLAP_MS,
) -> list[Chunk]:
    segs = [
        s
        for s in sorted(segments, key=lambda s: (s.start_ms, s.end_ms))
        if s.text and s.text.strip()
    ]
    chunks: list[Chunk] = []
    n = len(segs)
    i = 0
    while i < n:
        start = segs[i].start_ms
        j = i
        # Crece hasta el mínimo, sin pasarse del máximo.
        while j + 1 < n and segs[j + 1].end_ms - start <= target_max_ms:
            j += 1
            if (
                segs[j].end_ms - start >= target_min_ms
                and j + 1 < n
                and segs[j + 1].end_ms - start > target_max_ms
            ):
                break
        end = segs[j].end_ms
        text = " ".join(segs[k].text.strip() for k in range(i, j + 1)).strip()
        if text:
            chunks.append(
                Chunk(
                    video_id=video_id,
                    start_ms=start,
                    end_ms=end,
                    text=text,
                    token_count=estimate_tokens(text),
                )
            )
        # Siguiente trozo: primer segmento que solape con los últimos 15 s,
        # pero solo si queda contenido nuevo (más allá del final anterior);
        # si no, el solape generaría trozos basura al final.
        if segs[-1].end_ms <= end:
            break
        k = i + 1
        while k < n and segs[k].start_ms < end - overlap_ms:
            k += 1
        i = max(k, i + 1)
    return chunks
