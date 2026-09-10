"""Redacción de la respuesta con el LLM, con degradación limpia.

Requisito: la búsqueda funciona sin LLM. `synthesize` devuelve `None` si el chat
falla o está desactivado; la API sigue mostrando los fragmentos.
"""

from __future__ import annotations

import re

SYSTEM = (
    "Eres el redactor de Radar IA. Respondes en español, breve y directo. "
    "Usa SOLO los fragmentos numerados que te doy. Cada afirmación debe citar "
    "el fragmento con [n]. Si la respuesta no está en los fragmentos, dilo "
    "claramente y no inventes nada."
)


def build_prompt(question: str, results: list[dict]) -> str:
    lines = [f"Pregunta: {question}", "", "Fragmentos:"]
    for i, r in enumerate(results, start=1):
        lines.append(
            f"[{i}] {r['video_id']} @ {r['start_label']} — {r['title']} "
            f"({r['lang']}): {r['text']}"
        )
    return "\n".join(lines)


def synthesize(question: str, results: list[dict], ai, chat_model: str) -> str | None:
    if not results:
        return None
    try:
        return ai.chat(SYSTEM, build_prompt(question, results), chat_model)
    except Exception:  # noqa: BLE001 - sin LLM seguimos mostrando resultados
        return None


TRANSLATE_SYSTEM = (
    "Traduce al español cada fragmento numerado, de forma literal y breve. "
    "Responde SOLO con líneas con el formato 'id: traducción', una por fragmento."
)


def translate_snippets(results: list[dict], ai, chat_model: str) -> dict[int, str]:
    """Traduce los fragmentos que no están en español. Si falla, devuelve {}."""
    need = [r for r in results if r.get("lang") and not str(r["lang"]).startswith("es")]
    if not need:
        return {}
    body = "\n".join(f"{r['chunk_id']}: {r['text']}" for r in need)
    try:
        out = ai.chat(TRANSLATE_SYSTEM, body, chat_model)
    except Exception:  # noqa: BLE001
        return {}
    translations: dict[int, str] = {}
    for line in out.splitlines():
        match = re.match(r"\s*\[?(\d+)\]?\s*[:.\-]\s*(.+)", line)
        if match:
            translations[int(match.group(1))] = match.group(2).strip()
    return translations

