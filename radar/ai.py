"""Cliente del proveedor compatible con OpenAI: embeddings y chat.

Usa el SDK oficial apuntando `base_url` al proveedor configurado. Los nombres de
modelo no se hardcodean: si CHAT_MODEL/EMBEDDING_MODEL están vacíos se eligen de
GET {base}/models por coincidencia de nombre.

Rendimiento:
- La lista de modelos y el cliente se cachean a nivel de módulo; GET /models no
  se repite en cada búsqueda.
- Los embeddings de consultas repetidas se cachean en memoria.
- Por defecto se desactiva el "razonamiento" del modelo de chat, que multiplica
  la latencia sin mejorar una respuesta corta con citas.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict

from openai import OpenAI

from .config import Settings


class AIError(RuntimeError):
    pass


def _pick(models: list[str], preferred: str, needle: str) -> str | None:
    if preferred and preferred in models:
        return preferred
    if preferred and not models:
        return preferred  # el proveedor no lista modelos pero el usuario lo fijó
    for model in models:
        if needle.lower() in model.lower():
            return model
    return None


_MODELS_CACHE: dict[tuple[str, str], list[str]] = {}
_CLIENTS: dict[tuple[str, str], "AIClient"] = {}
_EMBED_CACHE: "OrderedDict[tuple[str, str], list[float]]" = OrderedDict()
_EMBED_MAX = 512
_EMBED_LOCK = threading.Lock()


class AIClient:
    def __init__(self, settings: Settings):
        if not settings.ai_base_url or not settings.ai_key:
            raise AIError(
                "Falta AI_API_BASE_URL o AI_API_KEY en .env. "
                "Son necesarias para embeddings y para redactar respuestas."
            )
        self.settings = settings
        self._client = OpenAI(base_url=settings.ai_base_url, api_key=settings.ai_key)

    def models(self) -> list[str]:
        key = (self.settings.ai_base_url, self.settings.ai_key)
        if key not in _MODELS_CACHE:
            try:
                _MODELS_CACHE[key] = [m.id for m in self._client.models.list().data]
            except Exception as exc:  # noqa: BLE001 - mensaje claro al usuario
                raise AIError(
                    f"No se pudo obtener la lista de modelos de {self.settings.ai_base_url}: {exc}. "
                    "Revisa AI_API_BASE_URL y AI_API_KEY."
                ) from exc
        return _MODELS_CACHE[key]

    def resolve_embedding(self) -> str:
        model = _pick(self.models(), self.settings.embedding_model, "embed")
        if not model:
            raise AIError(
                "No encontré un modelo de embeddings en la lista del proveedor. "
                "Define EMBEDDING_MODEL en .env."
            )
        return model

    def resolve_chat(self) -> str:
        preferred = self.settings.chat_model or "deepseek-v4-flash"
        model = _pick(self.models(), preferred, "flash")
        if not model:
            raise AIError(
                "No encontré un modelo de chat en la lista del proveedor. "
                "Define CHAT_MODEL en .env."
            )
        return model

    def _embed_raw(self, texts: list[str], model: str) -> list[list[float]]:
        resp = self._client.embeddings.create(model=model, input=texts)
        return [list(item.embedding) for item in resp.data]

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        """Embeddings con caché por (modelo, texto)."""
        results: list[list[float] | None] = [None] * len(texts)
        missing: list[tuple[int, str]] = []
        with _EMBED_LOCK:
            for index, text in enumerate(texts):
                key = (model, hashlib.sha256(text.encode("utf-8")).hexdigest())
                cached = _EMBED_CACHE.get(key)
                if cached is not None:
                    _EMBED_CACHE.move_to_end(key)
                    results[index] = cached
                else:
                    missing.append((index, text))
        if missing:
            vectors = self._embed_raw([text for _, text in missing], model)
            with _EMBED_LOCK:
                for (index, text), vector in zip(missing, vectors):
                    results[index] = vector
                    key = (model, hashlib.sha256(text.encode("utf-8")).hexdigest())
                    _EMBED_CACHE[key] = vector
                    if len(_EMBED_CACHE) > _EMBED_MAX:
                        _EMBED_CACHE.popitem(last=False)
        return results  # type: ignore[return-value]

    def chat(self, system: str, user: str, model: str, max_tokens: int = 700) -> str:
        kwargs: dict = {"temperature": 0.2, "max_tokens": max_tokens}
        if self.settings.disable_reasoning:
            # vLLM/OpenAI-compatible: evita los tokens de razonamiento.
            kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
        resp = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **kwargs,
        )
        return resp.choices[0].message.content or ""


def get_client(settings: Settings) -> AIClient:
    """Cliente compartido por proceso (la lista de modelos va cacheada dentro)."""
    key = (settings.ai_base_url, settings.ai_key)
    client = _CLIENTS.get(key)
    if client is None:
        client = AIClient(settings)
        _CLIENTS[key] = client
    return client
