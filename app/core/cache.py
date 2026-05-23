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
import fnmatch
from typing import Any, Optional
import redis.asyncio as aioredis
import structlog

from app.core.config import settings

log = structlog.get_logger()
_redis: Any = None
_local_store = {}


class NullCache:
    """In-memory fallback when Redis is unavailable or intentionally disabled."""
    async def get(self, key: str):
        return _local_store.get(key)

    async def setex(self, key: str, ttl: int, value: str):
        _local_store[key] = value
        return True

    async def delete(self, *keys: str):
        count = 0
        for k in keys:
            if k in _local_store:
                del _local_store[k]
                count += 1
        return count

    async def keys(self, pattern: str):
        return fnmatch.filter(_local_store.keys(), pattern)

    async def exists(self, *keys: str):
        return sum(1 for k in keys if k in _local_store)

    async def ping(self):
        return True

    async def close(self):
        return None


async def init_cache():
    global _redis
    # Handle intentional disable via config
    if not settings.REDIS_URL or settings.REDIS_URL.lower() in ["", "none", "disabled", "false"]:
        _redis = NullCache()
        log.info("cache.init", status="in_memory_mode", reason="REDIS_URL is empty or disabled")
        return

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
    CAPTCHA = "auth:captcha:{captcha_id}"

    @staticmethod
    def exam_pattern(exam_id: str) -> str:
        """Return glob pattern to wipe all cache related to one exam."""
        return f"*exam*{exam_id}*"
