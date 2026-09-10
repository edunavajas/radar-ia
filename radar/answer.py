"""Redacción de la respuesta con el LLM, con degradación limpia.

Requisito: la búsqueda funciona sin LLM. `synthesize` devuelve `None` si el chat
falla o está desactivado; la API sigue mostrando los fragmentos.
"""

from __future__ import annotations

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
