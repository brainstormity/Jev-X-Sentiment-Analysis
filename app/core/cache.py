import time
from typing import Any, Optional, Dict, Tuple
import asyncio


class TTLCache:
    """
    In-memory async-safe TTL cache.
    Keys expire after ttl_seconds.
    """
    def __init__(self, default_ttl: int = 600):
        self._default_ttl = default_ttl
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key not in self._cache:
                return None
            value, expires_at = self._cache[key]
            if time.time() > expires_at:
                del self._cache[key]
                return None
            return value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        async with self._lock:
            ttl_seconds = ttl if ttl is not None else self._default_ttl
            expires_at = time.time() + ttl_seconds
            self._cache[key] = (value, expires_at)

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()


# Global cache instance for social data and market ticks
social_cache = TTLCache(default_ttl=600)  # 10 minutes
market_cache = TTLCache(default_ttl=60)   # 1 minute
