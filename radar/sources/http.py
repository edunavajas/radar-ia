"""HTTP con caché en disco y rate limiting suave.

RSS y oEmbed son gratis, pero no conviene machacarlos: mínimo `min_interval`
segundos entre peticiones reales. Las respuestas se cachean en disco, así que
una segunda ejecución no vuelve a pedirlas.
"""

from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path

import httpx

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Cookie de consentimiento: sin ella YouTube redirige a consent.youtube.com.
DEFAULT_COOKIES = {
    "SOCS": (
        "CAISNQgDEitib3FfaWRlbnRpdHlmcm9udGVuZHVpc2VydmVyXzIwMjMwODI5LjA3X3Ax"
        "GgJlbiACGgYIgLC_pwY"
    )
}


class CachedHttp:
    def __init__(
        self,
        cache_dir: Path | str,
        min_interval: float = 0.5,
        timeout: float = 30.0,
        fetch=None,
    ):
        self.cache_dir = Path(cache_dir)
        self.min_interval = min_interval
        self._fetch_override = fetch
        self._client = (
            None
            if fetch
            else httpx.Client(
                timeout=timeout,
                headers=DEFAULT_HEADERS,
                cookies=DEFAULT_COOKIES,
                follow_redirects=True,
            )
        )
        self._lock = threading.Lock()
        self._last_request = 0.0

    def get(self, url: str, kind: str = "http") -> bytes:
        cache_path = self.cache_dir / kind / (
            hashlib.sha256(url.encode()).hexdigest() + ".cache"
        )
        if cache_path.exists():
            return cache_path.read_bytes()
        self._wait_turn()
        content = self._request(url)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(content)
        return content

    def get_text(self, url: str, kind: str = "http") -> str:
        return self.get(url, kind).decode("utf-8", "replace")

    def _wait_turn(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_request
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last_request = time.monotonic()

    def _request(self, url: str) -> bytes:
        if self._fetch_override is not None:
            return self._fetch_override(url)
        assert self._client is not None
        resp = self._client.get(url)
        resp.raise_for_status()
        return resp.content

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
