"""Cliente del proveedor compatible con OpenAI: embeddings y chat.

Usa el SDK oficial apuntando `base_url` al proveedor configurado. Los nombres de
modelo no se hardcodean: si CHAT_MODEL/EMBEDDING_MODEL están vacíos se eligen de
GET {base}/models por coincidencia de nombre, y si la llamada falla se avisa con
un mensaje claro.
"""

from __future__ import annotations

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


class AIClient:
    def __init__(self, settings: Settings):
        if not settings.ai_base_url or not settings.ai_key:
            raise AIError(
                "Falta AI_API_BASE_URL o AI_API_KEY en .env. "
                "Son necesarias para embeddings y para redactar respuestas."
            )
        self.settings = settings
        self._client = OpenAI(base_url=settings.ai_base_url, api_key=settings.ai_key)
        self._models: list[str] | None = None

    def models(self) -> list[str]:
        if self._models is None:
            try:
                self._models = [m.id for m in self._client.models.list().data]
            except Exception as exc:  # noqa: BLE001 - mensaje claro al usuario
                raise AIError(
                    f"No se pudo obtener la lista de modelos de {self.settings.ai_base_url}: {exc}. "
                    "Revisa AI_API_BASE_URL y AI_API_KEY."
                ) from exc
        return self._models

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

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        resp = self._client.embeddings.create(model=model, input=texts)
        return [list(item.embedding) for item in resp.data]

    def chat(self, system: str, user: str, model: str) -> str:
        resp = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content or ""
