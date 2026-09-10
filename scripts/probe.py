#!/usr/bin/env python3
"""Probe de la API de Thordata: una sola peticion de transcripcion.

Lanza exactamente una peticion `youtube_transcript_by-id` para un unico
video_id, imprime el status y el cuerpo crudo, y guarda la respuesta en
samples/. No asume la forma de la respuesta: es el unico codigo autorizado a
"no saber" como responde la API. A partir de su salida se escribe el parser.

Uso:
    python scripts/probe.py [video_id] [lang]

Sin dependencias externas: solo la libreria estandar, para poder ejecutarlo
antes de montar nada.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
ENDPOINT = "https://scraperapi.thordata.com/builder"
# La doc oficial usa "www.youtube.com" en el ejemplo de subtitulos.
SPIDER_NAME = "www.youtube.com"
SPIDER_ID = "youtube_transcript_by-id"


def load_env(path: Path) -> None:
    """Carga .env minimo sin dependencias. No pisa variables ya definidas."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def build_request(token: str, video_id: str, lang: str) -> Request:
    form = {
        "spider_name": SPIDER_NAME,
        "spider_id": SPIDER_ID,
        "spider_parameters": json.dumps([{"video_id": video_id}]),
        "spider_universal": json.dumps(
            {"subtitles_language": lang, "subtitles_type": "auto_generated"}
        ),
        "spider_errors": "true",
        "file_name": "{{TasksID}}",
    }
    return Request(
        ENDPOINT,
        data=urlencode(form).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )


def main() -> int:
    load_env(ROOT / ".env")

    token = os.environ.get("THORDATA_TOKEN", "").strip()
    if not token:
        print("ERROR: THORDATA_TOKEN esta vacio. Rellenalo en .env y reintenta.")
        return 2

    video_id = sys.argv[1] if len(sys.argv) > 1 else "8RePenzQH80"
    lang = sys.argv[2] if len(sys.argv) > 2 else "en"

    print(f"POST {ENDPOINT}")
    print(f"  spider_id={SPIDER_ID}  video_id={video_id}  lang={lang}")

    try:
        with urlopen(build_request(token, video_id, lang), timeout=120) as resp:
            status, headers, raw = resp.status, resp.headers, resp.read()
    except HTTPError as exc:  # 4xx/5xx: la respuesta cruda es el dato
        status, headers, raw = exc.code, exc.headers, exc.read()
    except URLError as exc:
        print(f"ERROR de red: {exc.reason}")
        return 1

    print(f"HTTP {status}  content-type={headers.get('Content-Type')}")
    print("--- cuerpo crudo ---")
    print(raw.decode("utf-8", "replace"))

    SAMPLES.mkdir(exist_ok=True)
    out = SAMPLES / f"probe-{video_id}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_bytes(raw)
    print(f"\nRespuesta guardada en {out}")
    return 0 if status < 400 else 1


if __name__ == "__main__":
    raise SystemExit(main())
