"""
app/core/cache.py

Cache-aside (lazy loading) strategy — Module 2: Cache + Load Balancing.

Pattern:
  1. Read hit  → return from cache
  2. Read miss → fetch from DB, store in cache, return
  3. Write     → update DB, then invalidate cache (not update)

Benefits demonstrated:
  - LLM hint responses cached → save 90% AI API cost
  - Exam/package listings cached → ~10ms vs ~200ms cold DB read
  - Leaderboard cached with short TTL → eventual consistency acceptable
"""
import json
from typing import Any, Optional
import redis.asyncio as aioredis
import structlog

from app.core.config import settings

log = structlog.get_logger()
_redis: Any = None


class NullCache:
    async def get(self, key: str):
        return None

    async def setex(self, key: str, ttl: int, value: str):
        return False

    async def delete(self, *keys: str):
        return 0

    async def keys(self, pattern: str):
        return []

    async def exists(self, *keys: str):
        return 0

    async def ping(self):
        return False

    async def close(self):
        return None


async def init_cache():
    global _redis
    try:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await _redis.ping()
        log.info("cache.connected", url=settings.REDIS_URL)
    except Exception as e:
        log.warning("cache.disabled", url=settings.REDIS_URL, error=str(e))
        _redis = NullCache()


async def close_cache():
    global _redis
    if _redis:
        await _redis.close()


def get_cache() -> Any:
    global _redis
    if _redis is None:
        _redis = NullCache()
    return _redis


# ─── Cache helpers ───────────────────────────────────────────────────────────

async def cache_get(key: str) -> Optional[Any]:
    """Return deserialized value or None on cache miss."""
    try:
        raw = await _redis.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        log.warning("cache.get_error", key=key, error=str(e))
        return None  # degrade gracefully — never let cache crash the app


async def cache_set(key: str, value: Any, ttl: int = None) -> bool:
    """Serialize and store value. Returns True on success."""
    try:
        ttl = ttl or settings.CACHE_DEFAULT_TTL
        await _redis.setex(key, ttl, json.dumps(value, default=str))
        return True
    except Exception as e:
        log.warning("cache.set_error", key=key, error=str(e))
        return False


async def cache_delete(key: str) -> bool:
    """Invalidate a single cache key."""
    try:
        await _redis.delete(key)
        return True
    except Exception as e:
        log.warning("cache.delete_error", key=key, error=str(e))
        return False


async def cache_delete_pattern(pattern: str) -> int:
    """Invalidate all keys matching a glob pattern. Use for group invalidation."""
    try:
        keys = await _redis.keys(pattern)
        if keys:
            await _redis.delete(*keys)
        return len(keys)
    except Exception as e:
        log.warning("cache.pattern_delete_error", pattern=pattern, error=str(e))
        return 0


# ─── Cache key builders (centralised to avoid key typos — DRY) ───────────────

class CacheKeys:
    EXAM_LIST = "exams:list:{category}:{page}"
    EXAM_DETAIL = "exams:detail:{slug}"
    PACKAGE_LIST = "packages:exam:{exam_id}"
    QUESTION_LIST = "questions:package:{package_id}"
    LEADERBOARD = "leaderboard:exam:{exam_id}:top{n}"
    USER_PURCHASES = "purchases:user:{user_id}"
    CERT_METADATA_CATEGORIES = "cert_metadata:categories"
    CERT_METADATA_CERTIFICATIONS = "cert_metadata:certifications"
    AI_HINT = "ai:hint:q:{question_id}:u:{user_id}"   # short TTL — personalized
    AI_EXPLAIN = "ai:explain:q:{question_id}"          # longer TTL — shared

    @staticmethod
    def exam_pattern(exam_id: str) -> str:
        """Return glob pattern to wipe all cache related to one exam."""
        return f"*exam*{exam_id}*"
