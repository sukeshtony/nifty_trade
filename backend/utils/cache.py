"""In-memory cache for live market data using a simple dict store."""

import time
from typing import Any, Dict, Optional
import threading


class MarketCache:
    """Thread-safe in-memory cache with TTL support."""

    def __init__(self, default_ttl: int = 60):
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        with self._lock:
            self._store[key] = {
                "value": value,
                "expires_at": time.time() + (ttl or self._default_ttl),
            }

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._store.get(key)
            if not item:
                return None
            if time.time() > item["expires_at"]:
                del self._store[key]
                return None
            return item["value"]

    def get_or_default(self, key: str, default: Any = None) -> Any:
        val = self.get(key)
        return val if val is not None else default

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def keys(self) -> list:
        with self._lock:
            now = time.time()
            return [k for k, v in self._store.items() if now <= v["expires_at"]]


# Global singleton
cache = MarketCache(default_ttl=120)
