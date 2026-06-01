"""
app/middleware/

Middleware stack covering:
  - Auth: JWT validation as FastAPI dependency
  - Rate limiting: token-bucket per IP via Redis (Module 2)
  - Request logging: structured JSON logs (Module 3: Observability)
  - CORS: frontend origin whitelist (Module 2: Security)
"""
import time
import uuid
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import structlog

from app.core.config import settings
from app.core.database import get_db
from app.core.cache import get_cache
from app.core.security import decode_token, is_token_blacklisted

log = structlog.get_logger()
bearer_scheme = HTTPBearer(auto_error=False)


# ─── Auth Dependency ─────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    """
    FastAPI dependency — validates JWT and returns current user doc.
    Raises 401 if token is missing, invalid, or blacklisted.
    """
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = credentials.credentials
    if await is_token_blacklisted(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    db = get_db()
    from bson import ObjectId
    user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user


async def get_current_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency that requires admin role."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[dict]:
    """Auth dependency that doesn't raise — returns None for unauthenticated requests."""
    if not credentials:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


# ─── Rate Limiting ────────────────────────────────────────────────────────────
# Module 2: Solutions Architect — protect against DDoS and API abuse

class RateLimiter:
    """
    Token bucket rate limiter using Redis.
    Each IP gets RATE_LIMIT_PER_MINUTE tokens per minute.
    """
    def __init__(self, limit: int = None, window: int = 60):
        self.limit = limit or settings.RATE_LIMIT_PER_MINUTE
        self.window = window

    async def __call__(self, request: Request):
        cache = get_cache()
        ip = request.client.host if request.client else "unknown"
        key = f"ratelimit:{ip}"

        # Atomic increment + set expiry (Lua would be ideal, this is demo)
        count = await cache.incr(key)
        if count == 1:
            await cache.expire(key, self.window)

        if count > self.limit:
            log.warning("rate_limit.exceeded", ip=ip, count=count)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: {self.limit} requests/minute",
                headers={"Retry-After": str(self.window)},
            )

        return {"ip": ip, "count": count, "limit": self.limit}


rate_limit = RateLimiter()


# ─── Logging Middleware ───────────────────────────────────────────────────────
# Module 3: Observability — metrics, logs, traces

async def logging_middleware(request: Request, call_next):
    """
    Structured request/response logging — Module 3 (Performance Monitoring).
    Emits: method, path, status_code, duration_ms, request_id.
    """
    request_id = str(uuid.uuid4())[:8]
    start = time.monotonic()

    # log.info(
    #     "request.start",
    #     request_id=request_id,
    #     method=request.method,
    #     path=request.url.path,
    #     ip=request.client.host if request.client else "unknown",
    # )

    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        log.error(
            "request.error",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            duration_ms=duration_ms,
            error=str(exc),
        )
        raise

    duration_ms = round((time.monotonic() - start) * 1000, 2)
    # log.info(
    #     "request.complete",
    #     request_id=request_id,
    #     method=request.method,
    #     path=request.url.path,
    #     status_code=response.status_code,
    #     duration_ms=duration_ms,
    # )

    # Add observability headers
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Duration-MS"] = str(duration_ms)
    return response
