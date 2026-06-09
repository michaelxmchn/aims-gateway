"""Storage abstraction — Redis-backed KV store with in-memory fallback (Layer 3.5).

Reads ``REDIS_URL`` from the environment.  When set, all operations go through
Redis (persistent across container restarts on Fly.io).  When unset, falls back
to a thread-safe ``dict`` — suitable for local development and testing.

Usage::

    store = Storage()
    store.set("key", {"nested": "value"})
    val = store.get("key")   # → {"nested": "value"}
    store.delete("key")
    store.flushdb()          # clear everything
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

REDIS_URL_ENV = "REDIS_URL"


class Storage:
    """Key-value persistence with automatic Redis / in-memory fallback.

    Serialises values as JSON so nested dicts, lists, and primitives all
    work transparently.
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url = redis_url or os.getenv(REDIS_URL_ENV, "")
        self._local: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._redis = None

        if self._redis_url:
            try:
                import redis as _redis

                self._redis = _redis.from_url(
                    self._redis_url,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
                self._redis.ping()
                logger.info("Storage connected to Redis at %s", self._redis_url)
            except Exception:
                logger.warning(
                    "Redis at %s unreachable — falling back to in-memory storage",
                    self._redis_url,
                )
                self._redis = None

    @property
    def is_persistent(self) -> bool:
        """``True`` when the backend is Redis (survives restarts)."""
        return self._redis is not None

    # ── Public API ──────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value by *key*, or return *default* when missing."""
        if self._redis:
            raw = self._redis.get(key)
            return json.loads(raw) if raw is not None else default
        with self._lock:
            raw = self._local.get(key)
            return json.loads(raw) if raw is not None else default

    def set(self, key: str, value: Any) -> None:
        """Persist *value* (JSON-serialisable) at *key*."""
        payload = json.dumps(value, default=str)
        if self._redis:
            self._redis.set(key, payload)
        else:
            with self._lock:
                self._local[key] = payload

    def delete(self, key: str) -> None:
        """Remove *key* from the store (no-op if missing)."""
        if self._redis:
            self._redis.delete(key)
        else:
            with self._lock:
                self._local.pop(key, None)

    def exists(self, key: str) -> bool:
        """Check whether *key* exists in the store."""
        if self._redis:
            return bool(self._redis.exists(key))
        with self._lock:
            return key in self._local

    def keys(self, pattern: str = "*") -> list[str]:
        """Return all keys matching *pattern* (glob-style)."""
        if self._redis:
            return self._redis.keys(pattern)
        with self._lock:
            return list(self._local.keys())

    def flushdb(self) -> None:
        """Remove all keys from the store (use with care)."""
        if self._redis:
            self._redis.flushdb()
        else:
            with self._lock:
                self._local.clear()
