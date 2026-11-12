"""Thread-safe in-memory TTL caching layer for high-throughput API gateway and public endpoints."""

from functools import wraps
import os
import sys
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

_bypass_cache_in_tests = True


def set_test_cache_bypass(bypass: bool) -> None:
    global _bypass_cache_in_tests
    _bypass_cache_in_tests = bypass


class TTLCache:
    """Thread-safe in-memory cache with per-item TTL and max size eviction."""

    def __init__(self, maxsize: int = 1024, default_ttl: float = 60.0) -> None:
        self.maxsize = maxsize
        self.default_ttl = default_ttl
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        if _bypass_cache_in_tests and ("pytest" in sys.modules or bool(os.getenv("PYTEST_CURRENT_TEST"))):
            return None
        now = time.monotonic()
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if now > expires_at:
                self._cache.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        now = time.monotonic()
        expiry = now + (ttl if ttl is not None else self.default_ttl)
        with self._lock:
            if len(self._cache) >= self.maxsize:
                # Evict expired first
                expired_keys = [k for k, (exp, _) in self._cache.items() if exp <= now]
                for k in expired_keys:
                    self._cache.pop(k, None)
                # If still at capacity, evict oldest 10%
                if len(self._cache) >= self.maxsize:
                    keys_to_remove = list(self._cache.keys())[: max(1, self.maxsize // 10)]
                    for k in keys_to_remove:
                        self._cache.pop(k, None)
            self._cache[key] = (expiry, value)

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._cache.pop(key, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._cache)


# Dedicated cache instances
_branding_cache = TTLCache(maxsize=32, default_ttl=60.0)
_plans_cache = TTLCache(maxsize=32, default_ttl=60.0)
_overview_cache = TTLCache(maxsize=64, default_ttl=60.0)
_key_auth_cache = TTLCache(maxsize=4096, default_ttl=30.0)


def get_branding_cache() -> TTLCache:
    return _branding_cache


def get_plans_cache() -> TTLCache:
    return _plans_cache


def get_overview_cache() -> TTLCache:
    return _overview_cache


def get_key_auth_cache() -> TTLCache:
    return _key_auth_cache


def invalidate_branding_cache() -> None:
    _branding_cache.clear()
    _overview_cache.clear()


def invalidate_plans_cache() -> None:
    _plans_cache.clear()
    _overview_cache.clear()


def invalidate_overview_cache() -> None:
    _overview_cache.clear()


def invalidate_key_auth_cache(key_hash: Optional[str] = None) -> None:
    if key_hash:
        _key_auth_cache.delete(key_hash)
    else:
        _key_auth_cache.clear()
