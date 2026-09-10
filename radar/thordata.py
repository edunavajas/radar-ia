"""Cliente de Thordata: lanzar tareas, esperar y descargar resultados.

Ciclo:
  POST /video_builder            -> identificador de tarea
  POST /tasks-download (token)   -> {"code":200,"data":{"download":url}}
  GET  url                       -> guardar crudo en samples/raw/ y parsear

Polling con backoff 5 s → 60 s, timeout total 10 min. Sin webhooks ni S3.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from .config import Settings

POLL_START_S = 5
POLL_MAX_S = 60
POLL_TIMEOUT_S = 600


class ThordataError(RuntimeError):
    pass


class CreditsExhausted(ThordataError):
    """La cuenta no tiene créditos de scraper. Mensaje claro, no stacktrace."""


class TaskNotReady(ThordataError):
    pass


class TaskTimeout(ThordataError):
    pass


_CREDITS_MSG = (
    "La cuenta de Thordata no tiene créditos de scraper o los ha agotado. "
    "Recarga créditos para usar la ingesta --live; mientras tanto, "
    "usa --from-samples o el seed."
)


def _safe_json(resp: httpx.Response) -> Any | None:
    try:
        return resp.json()
    except Exception:
        return None


def _has_credit_error(text: str) -> bool:
    lowered = text.lower()
    return any(w in lowered for w in ("insufficient credit", "no credit", "balance", "quota"))


def raise_for_credits(resp: httpx.Response, payload: Any | None = None) -> None:
    """Detecta falta de créditos aunque venga con HTTP 200 y código 402 en el cuerpo."""
    if resp.status_code == 402:
        raise CreditsExhausted(_CREDITS_MSG)
    if resp.status_code >= 400 and _has_credit_error(resp.text):
        raise CreditsExhausted(_CREDITS_MSG)
    if isinstance(payload, dict):
        code = payload.get("code")
        message = " ".join(
            str(payload.get(k, "")) for k in ("data", "msg", "message")
        )
        if code == 402 or _has_credit_error(message) or _has_credit_error(resp.text):
            raise CreditsExhausted(_CREDITS_MSG)


def _business_error(payload: Any, raw: str) -> None:
    """code != 200 en el cuerpo (códigos propios de Thordata)."""
    if isinstance(payload, dict) and payload.get("code") not in (0, 200, None):
        raise ThordataError(
            f"Thordata código {payload.get('code')}: "
            f"{payload.get('data') or payload.get('msg') or raw[:200]}"
        )



_TASK_ID_KEYS = ("tasks_id", "tasks_ids", "task_id", "taskId", "id")


def _extract_task_id(payload: Any, raw: str) -> str:
    """Extrae el id de tarea. Claves tanteadas: se ajusta al ver una respuesta real."""
    candidates: list[Any] = []
    if isinstance(payload, dict):
        candidates.append(payload)
        for key in ("data", "result", "results"):
            if isinstance(payload.get(key), dict):
                candidates.append(payload[key])
    for obj in candidates:
        for key in _TASK_ID_KEYS:
            value = obj.get(key)
            if value:
                return str(value)
    raise ThordataError(
        "No se encontró el identificador de tarea en la respuesta de Thordata. "
        f"Respuesta: {raw[:300]}"
    )


class ThordataClient:
    def __init__(self, settings: Settings, timeout: float = 60.0):
        self.settings = settings
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ThordataClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def launch(self, request: dict) -> str:
        """Lanza una tarea y devuelve su identificador."""
        form = {
            "spider_name": "youtube.com",
            "spider_id": request["spider_id"],
            "spider_parameters": json.dumps(request["spider_parameters"], ensure_ascii=False),
            "spider_errors": "true",
            "file_name": request.get("file_name", "{{VideoID}}"),
        }
        if "spider_universal" in request:
            form["spider_universal"] = json.dumps(
                request["spider_universal"], ensure_ascii=False
            )
        resp = self._client.post(
            self.settings.builder_url,
            data=form,
            headers={"Authorization": f"Bearer {self.settings.thordata_token}"},
        )
        payload = _safe_json(resp)
        raise_for_credits(resp, payload)
        if resp.status_code >= 400:
            raise ThordataError(f"Thordata {resp.status_code}: {resp.text[:300]}")
        _business_error(payload, resp.text)
        return _extract_task_id(payload, resp.text)

    def download(self, tasks_id: str, type_: str = "json") -> str:
        """Devuelve la URL de descarga; lanza TaskNotReady si aún no está lista."""
        resp = self._client.post(
            self.settings.download_url,
            data={"tasks_id": tasks_id, "type": type_},
            headers={"token": self.settings.thordata_token},
        )
        payload = _safe_json(resp)
        raise_for_credits(resp, payload)
        if resp.status_code >= 400:
            raise ThordataError(f"Thordata {resp.status_code}: {resp.text[:300]}")
        if not isinstance(payload, dict) or payload.get("code") != 200:
            msg = payload.get("msg") if isinstance(payload, dict) else resp.text[:200]
            raise TaskNotReady(f"Tarea {tasks_id} no lista: {msg}")
        url = (payload.get("data") or {}).get("download")
        if not url:
            raise TaskNotReady(f"Tarea {tasks_id} sin URL de descarga")
        return str(url)

    def poll(
        self,
        tasks_id: str,
        type_: str = "json",
        start_s: int = POLL_START_S,
        cap_s: int = POLL_MAX_S,
        timeout_s: int = POLL_TIMEOUT_S,
    ) -> str:
        deadline = time.monotonic() + timeout_s
        delay = start_s
        while True:
            try:
                return self.download(tasks_id, type_)
            except TaskNotReady:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TaskTimeout(
                        f"La tarea {tasks_id} no estuvo lista en {timeout_s}s"
                    ) from None
                time.sleep(min(delay, remaining))
                delay = min(delay * 2, cap_s)

    def fetch(self, url: str) -> bytes:
        resp = self._client.get(url)
        resp.raise_for_status()
        return resp.content

    def fetch_text(self, url: str) -> str:
        return self.fetch(url).decode("utf-8", "replace")

    def poll_and_save(
        self, tasks_id: str, raw_path: Path | str, type_: str = "json"
    ) -> Path:
        """Espera el resultado, lo descarga y lo guarda crudo antes de parsear."""
        url = self.poll(tasks_id, type_)
        content = self.fetch(url)
        raw_path = Path(raw_path)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(content)
        return raw_path
