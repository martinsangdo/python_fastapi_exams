"""
app/core/security.py

Security implementations covering Module 2 (Security) + Module 3 (DevSecOps):
- bcrypt password hashing (never store plain text)
- JWT access + refresh token pair
- Token blacklist via Redis (logout support)
- OWASP: input sanitization helpers
- Prompt injection detection (Module 5 / AI Security)
"""
import re
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
import bcrypt
import structlog

from app.core.config import settings
from app.core.cache import get_cache

log = structlog.get_logger()

# ─── Password ────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """
    Hash a password using the bcrypt library directly.
    Bypasses passlib's internal 'detect_wrap_bug' which crashes with bcrypt 4.0+.
    """
    pre_hashed = hashlib.sha256(plain.encode()).hexdigest().encode()
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pre_hashed, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        pre_hashed = hashlib.sha256(plain.encode()).hexdigest().encode()
        return bcrypt.checkpw(pre_hashed, hashed.encode("utf-8"))
    except Exception:
        return False

# ─── JWT ─────────────────────────────────────────────────────────────────────

def create_access_token(subject: str, extra: dict = None) -> str:
    payload = {
        "sub": subject,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": datetime.now(timezone.utc),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str) -> str:
    payload = {
        "sub": subject,
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


async def blacklist_token(token: str, expire_seconds: int = None):
    """Add token to Redis blacklist on logout (Module 2: Security)."""
    cache = get_cache()
    ttl = expire_seconds or settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    await cache.setex(f"blacklist:{token}", ttl, "1")


async def is_token_blacklisted(token: str) -> bool:
    cache = get_cache()
    return await cache.exists(f"blacklist:{token}") == 1


# ─── OWASP hardening helpers ─────────────────────────────────────────────────

# OWASP: prevent XSS by stripping dangerous tags from any user-supplied text
_XSS_PATTERN = re.compile(r"<[^>]+>|javascript:|on\w+=", re.IGNORECASE)

def sanitize_text(text: str) -> str:
    """Strip potential XSS payloads. Apply to all free-text user inputs."""
    return _XSS_PATTERN.sub("", text).strip()


# SQL injection patterns (even though we use MongoDB, good defensive practice)
_SQLI_PATTERN = re.compile(
    r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|EXEC|EXECUTE)\b|--|;|'|\")",
    re.IGNORECASE
)

def looks_like_sqli(text: str) -> bool:
    return bool(_SQLI_PATTERN.search(text))


# ─── Prompt Injection Guard (Module 5: AI Security) ──────────────────────────

_INJECTION_PATTERNS = [
    r"ignore.*(previous|all|above).*instructions",
    r"forget.*(everything|your instructions|what you were told)",
    r"you are now",
    r"act as (a|an|if)",
    r"disregard (your|the|all)",
    r"system prompt",
    r"jailbreak",
    r"DAN mode",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE | re.DOTALL)


def detect_prompt_injection(text: str) -> bool:
    """
    Returns True if the text contains a likely prompt injection attack.
    Block or sanitize before passing to any LLM. (Module 5)
    """
    return bool(_INJECTION_RE.search(text))
