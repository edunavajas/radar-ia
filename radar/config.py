"""Configuración: carga de .env y ajustes del sistema."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path | None = None) -> None:
    """Carga un .env mínimo sin dependencias. No pisa variables ya definidas."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Settings:
    thordata_token: str
    ai_base_url: str
    ai_key: str
    chat_model: str
    embedding_model: str
    max_requests_per_run: int
    db_path: Path
    builder_url: str
    download_url: str
    no_llm: bool


def get_settings(load_dotenv: bool = True) -> Settings:
    if load_dotenv:
        load_env()
    return Settings(
        thordata_token=os.environ.get("THORDATA_TOKEN", "").strip(),
        ai_base_url=os.environ.get("AI_API_BASE_URL", "").strip().rstrip("/"),
        ai_key=os.environ.get("AI_API_KEY", "").strip(),
        chat_model=os.environ.get("CHAT_MODEL", "").strip(),
        embedding_model=os.environ.get("EMBEDDING_MODEL", "").strip(),
        max_requests_per_run=int(os.environ.get("MAX_REQUESTS_PER_RUN", "50") or 50),
        db_path=Path(os.environ.get("RADAR_DB", str(ROOT / "data" / "radar.db"))),
        builder_url=os.environ.get(
            "THORDATA_BUILDER_URL",
            "https://scraperapi.thordata.com/video_builder",
        ),
        download_url=os.environ.get(
            "THORDATA_DOWNLOAD_URL",
            "https://openapi.thordata.com/api/web-scraper-api/tasks-download",
        ),
        no_llm=os.environ.get("RADAR_NO_LLM", "").lower() in {"1", "true", "yes"},
    )
