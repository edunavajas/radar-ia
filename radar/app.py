"""API FastAPI + servido del frontend compilado en el mismo contenedor."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .ai import AIClient, AIError
from .answer import synthesize, translate_snippets
from .config import Settings, get_settings
from .search import hybrid_search, keyword_search
from .topics import week_topics

VERSION = "0.1.0"
STATIC_DIR = Path(__file__).resolve().parent / "static"

EMPTY_NOTICE = (
    "La base está vacía. Carga ejemplos con `make seed` o recolecta con "
    "`make ingest` (edita antes config/sources.yaml)."
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Radar IA", version=VERSION)

    def open_conn():
        conn = db.connect(settings.db_path)
        db.init_db(conn)
        return conn

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "version": VERSION}

    @app.get("/api/stats")
    def stats() -> dict:
        conn = open_conn()
        try:
            data = db.stats(conn)
            data["embedding_model"] = db.meta_get(conn, "embedding_model") or ""
            data["embedding_dim"] = db.meta_get(conn, "embedding_dim") or ""
            data["notice"] = EMPTY_NOTICE if data["empty"] else ""
            return data
        finally:
            conn.close()

    @app.get("/api/search")
    def search(
        q: str = Query(..., min_length=1),
        lang: str = "",
        channel: str = "",
        published_after: str = "",
        limit: int = 8,
    ) -> dict:
        conn = open_conn()
        try:
            if db.is_empty(conn):
                return {
                    "query": q,
                    "empty": True,
                    "answer": None,
                    "llm": False,
                    "results": [],
                    "notice": EMPTY_NOTICE,
                }
            filters = {
                key: value
                for key, value in {
                    "lang": lang,
                    "channel": channel,
                    "published_after": published_after,
                }.items()
                if value
            }

            ai = None
            model = ""
            try:
                ai = AIClient(settings)
                model = ai.resolve_embedding()
            except AIError:
                ai = None  # seguimos con BM25

            if ai is not None:
                results = hybrid_search(conn, ai, q, model, top_k=limit, filters=filters)
            else:
                results = keyword_search(conn, q, top_k=limit, filters=filters)

            answer = None
            if ai is not None and not settings.no_llm:
                chat_model = ai.resolve_chat()
                answer = synthesize(q, results, ai, chat_model)
                translations = translate_snippets(results, ai, chat_model)
                for item in results:
                    if item["chunk_id"] in translations:
                        item["translated"] = translations[item["chunk_id"]]

            return {
                "query": q,
                "empty": False,
                "answer": answer,
                "llm": bool(answer),
                "results": results,
            }
        finally:
            conn.close()

    @app.get("/api/week")
    def week(days: int = 7) -> dict:
        conn = open_conn()
        try:
            if db.is_empty(conn):
                return {"days": days, "topics": [], "notice": EMPTY_NOTICE}
            return {"days": days, "topics": week_topics(conn, days)}
        finally:
            conn.close()

    _mount_static(app)
    return app


def _mount_static(app: FastAPI) -> None:
    index = STATIC_DIR / "index.html"
    if not index.exists():
        @app.get("/", include_in_schema=False)
        def placeholder() -> HTMLResponse:
            return HTMLResponse(
                "<h1>Radar IA</h1><p>Frontend no compilado. Ejecuta "
                "<code>make build</code> (o <code>docker compose up --build</code>).</p>"
            )

        return

    assets = STATIC_DIR / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/", include_in_schema=False)
    def root() -> FileResponse:
        return FileResponse(index)

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        candidate = (STATIC_DIR / full_path).resolve()
        if candidate.is_file() and candidate.is_relative_to(STATIC_DIR.resolve()):
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()
