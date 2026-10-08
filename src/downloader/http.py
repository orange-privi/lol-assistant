from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests


class HttpClient:
    def __init__(
        self,
        timeout: int = 60,
        retries: int = 3,
        backoff: float = 1.5,
    ):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "lol-assistant-data/1.0",
                "Accept": "application/json",
            }
        )
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff

    def _get(self, url: str) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(self.backoff ** attempt)
        raise last_error  # type: ignore[misc]

    def get_json(self, url: str) -> Any:
        return self._get(url).json()

    def get_text(self, url: str) -> str:
        response = self._get(url)
        response.encoding = response.encoding or "utf-8"
        return response.text

    def save_json(
        self,
        url: str,
        path: Path,
        use_cache: bool = True,
    ) -> Any:
        """Fetch JSON and persist it. Reuses an existing file when cached."""
        if use_cache and path.exists():
            return json.loads(path.read_text(encoding="utf-8"))

        data = self.get_json(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return data

    def save_json_optional(
        self,
        url: str,
        path: Path,
        use_cache: bool = True,
    ) -> Any | None:
        """Like save_json but returns None instead of raising on failure."""
        try:
            return self.save_json(url, path, use_cache=use_cache)
        except Exception as exc:  # noqa: BLE001 - degraded source is tolerated
            print(f"[WARN] unavailable {url}: {exc}")
            return None
