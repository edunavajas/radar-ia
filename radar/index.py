"""Indexado: trocea transcripciones, genera embeddings y llena FTS5."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import db
from .ai import AIClient, AIError
from .chunking import chunk_segments
from .config import get_settings


@dataclass
class IndexSummary:
    videos_indexed: int = 0
    chunks_created: int = 0
    embeddings_added: int = 0
    ai_calls: int = 0
    embedding_model: str = ""
    dim: int = 0
    notes: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            "Resumen de indexado:",
            f"  vídeos troceados:     {self.videos_indexed}",
            f"  chunks creados:       {self.chunks_created}",
            f"  embeddings añadidos:  {self.embeddings_added}",
            f"  modelo embeddings:    {self.embedding_model or '(sin definir)'}",
            f"  dimensión detectada:  {self.dim or '-'}",
            f"  peticiones IA:        {self.ai_calls}",
        ]
        lines += [f"  nota: {n}" for n in self.notes]
        return "\n".join(lines)


def videos_pending_chunks(conn) -> list[str]:
    rows = conn.execute(
        """
        SELECT v.video_id FROM videos v
        WHERE EXISTS(SELECT 1 FROM segments s WHERE s.video_id = v.video_id)
          AND NOT EXISTS(SELECT 1 FROM chunks c WHERE c.video_id = v.video_id)
        """
    ).fetchall()
    return [r["video_id"] for r in rows]


def build_chunks(conn, summary: IndexSummary) -> None:
    for video_id in videos_pending_chunks(conn):
        chunks = chunk_segments(video_id, db.segments_for(conn, video_id))
        if not chunks:
            continue
        db.insert_chunks(conn, chunks)
        summary.videos_indexed += 1
        summary.chunks_created += len(chunks)
    conn.commit()


def rebuild(conn) -> None:
    conn.execute("DELETE FROM chunks_fts")
    conn.execute("DELETE FROM embeddings")
    conn.execute("DELETE FROM chunks")
    conn.commit()


def index_embeddings(
    conn, ai: AIClient, model: str, summary: IndexSummary, batch: int = 32
) -> None:
    first = True
    while True:
        pending = db.chunks_without_embedding(conn, model)[:batch]
        if not pending:
            break
        texts = [r["text"] for r in pending]
        vectors = ai.embed(texts, model)
        dim = len(vectors[0])
        if first:
            _check_dim(conn, model, dim, summary)
            db.meta_set(conn, "embedding_model", model)
            db.meta_set(conn, "embedding_dim", str(dim))
            summary.embedding_model = model
            summary.dim = dim
            first = False
        for row, vec in zip(pending, vectors):
            db.save_embedding(
                conn,
                row["id"],
                np.asarray(vec, dtype=np.float32).tobytes(),
                model,
                dim,
            )
        db.record_api_call(conn, "ai", "embeddings", {"n": len(texts), "model": model}, "ok")
        summary.embeddings_added += len(pending)
        summary.ai_calls += 1
        conn.commit()


def _check_dim(conn, model: str, dim: int, summary: IndexSummary) -> None:
    stored_dim = db.meta_get(conn, "embedding_dim")
    stored_model = db.meta_get(conn, "embedding_model")
    if stored_dim and (int(stored_dim) != dim or stored_model != model):
        summary.notes.append(
            f"AVISO: los vectores guardados son de {stored_model} (dim {stored_dim}) "
            f"y ahora se usa {model} (dim {dim}). Los vectores antiguos no valen: "
            "reindexa con --rebuild."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="radar.index", description="Indexado de Radar IA")
    parser.add_argument("--batch", type=int, default=32, help="tamaño de lote de embeddings")
    parser.add_argument("--rebuild", action="store_true", help="rehacer chunks y embeddings")
    args = parser.parse_args(argv)

    settings = get_settings()
    conn = db.connect(settings.db_path)
    db.init_db(conn)
    summary = IndexSummary()

    if args.rebuild:
        rebuild(conn)

    build_chunks(conn, summary)

    if not db.meta_get(conn, "embedding_dim") and db.stats(conn)["chunks"] == 0:
        print("No hay chunks que indexar. Ejecuta antes `make seed` o `make ingest`.")
        conn.close()
        return 0

    try:
        ai = AIClient(settings)
        model = ai.resolve_embedding()
        index_embeddings(conn, ai, model, summary, batch=args.batch)
    except AIError as exc:
        summary.notes.append(str(exc))
    finally:
        conn.commit()

    print(summary.render())
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
