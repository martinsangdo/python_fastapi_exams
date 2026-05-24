"""
app/services/auth_service.py

Authentication business logic — Module 1 (FastAPI MVC) + Module 2 (Security).
- Register with email uniqueness check
- Login with bcrypt verification
- JWT access + refresh token pair
- Token refresh and logout (blacklist)
"""
import uuid
import random
import string
import base64
from datetime import datetime, timezone
from typing import Optional, Any
import structlog

from app.core.config import settings
from app.core.database import get_db
from app.core.cache import cache_get, cache_set, cache_delete, cache_delete_pattern, CacheKeys
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    decode_token, blacklist_token, is_token_blacklisted,
)
from app.models.documents import new_user
from app.schemas.schemas import RegisterRequest, LoginRequest

log = structlog.get_logger()


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def generate_captcha() -> dict:
    captcha_id = str(uuid.uuid4())
    # Generate a simple 6-digit numeric captcha
    answer = ''.join(random.choices(string.digits, k=6))
    await cache_set(CacheKeys.CAPTCHA.format(captcha_id=captcha_id), answer, ttl=300)
    
    # Generate a simple SVG image locally to avoid external service issues
    # and ensure numbers are visible (DiceBear initials style often renders numbers as blank).
    image_data = _generate_svg_captcha(answer)

    return {
        "id": captcha_id,
        "image_url": image_data
    }

def _generate_svg_captcha(text: str) -> str:
    """Generate a simple SVG with text and noise lines, encoded as a data URI."""
    # dominant-baseline="middle" and text-anchor="middle" centers text in the viewport
    svg = f"""
    <svg width="150" height="50" xmlns="http://www.w3.org/2000/svg">
      <rect width="100%" height="100%" fill="#b6e3f4"/>
      <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" 
            font-family="monospace" font-size="28" font-weight="bold" fill="#003366" 
            transform="rotate({random.randint(-8, 8)} 75 25)">
        {text}
      </text>
      <line x1="0" y1="{random.randint(10, 40)}" x2="150" y2="{random.randint(10, 40)}" stroke="#003366" stroke-width="1" opacity="0.2"/>
      <line x1="{random.randint(10, 140)}" y1="0" x2="{random.randint(10, 140)}" y2="50" stroke="#003366" stroke-width="1" opacity="0.2"/>
    </svg>
    """.strip()
    b64 = base64.b64encode(svg.encode()).decode()
    return f"data:image/svg+xml;base64,{b64}"


async def register_user(data: RegisterRequest) -> dict:
    db = get_db()

    # Verify Captcha
    if not await _verify_captcha(data.captcha_id, data.captcha_answer):
        log.warning("auth.registration_failed_captcha", email=data.email, captcha_id=data.captcha_id)
        raise AuthError("Invalid or expired captcha", 400)

    # Check uniqueness (MongoDB unique index will also catch races, belt + braces)
    if await db.users.find_one({"email": data.email.lower()}):
        raise AuthError("Email already registered", 409)
    if await db.users.find_one({"username": data.username}):
        raise AuthError("Username already taken", 409)

    user_doc = new_user(
        email=data.email,
        username=data.username,
        hashed_password=hash_password(data.password),
    )
    user_doc["profile"]["full_name"] = data.full_name

    result = await db.users.insert_one(user_doc)
    user_doc["_id"] = result.inserted_id

    log.info("auth.registered", user_id=str(result.inserted_id), email=data.email)
    return _build_tokens(user_doc)


async def login_user(data: LoginRequest) -> dict:
    db = get_db()
    user = await db.users.find_one({"email": data.email.lower()})

    if not user or not verify_password(data.password, user["hashed_password"]):
        raise AuthError("Invalid email or password", 401)

    if not user.get("is_active", True):
        raise AuthError("Account is deactivated", 403)

    log.info("auth.login", user_id=str(user["_id"]))
    return _build_tokens(user)


async def refresh_tokens(refresh_token: str) -> dict:
    if await is_token_blacklisted(refresh_token):
        raise AuthError("Token has been revoked", 401)

    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise AuthError("Invalid refresh token", 401)

    db = get_db()
    from bson import ObjectId
    user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not user:
        raise AuthError("User not found", 401)

    # Rotate: blacklist old refresh token
    await blacklist_token(refresh_token, expire_seconds=7 * 24 * 3600)
    return _build_tokens(user)


async def logout_user(access_token: str, refresh_token: Optional[str] = None):
    await blacklist_token(access_token)
    if refresh_token:
        await blacklist_token(refresh_token, expire_seconds=7 * 24 * 3600)
    log.info("auth.logout")


async def _verify_captcha(captcha_id: str, answer: Any) -> bool:
    if not captcha_id or answer is None:
        log.warning("auth.captcha_missing_input", captcha_id=captcha_id, has_answer=answer is not None)
        return False

    # Development Master Key: Bypass captcha in dev mode
    if settings.APP_ENV == "development" and str(answer) == "000000":
        log.info("auth.captcha_bypass", captcha_id=captcha_id)
        return True

    key = CacheKeys.CAPTCHA.format(captcha_id=captcha_id)
    stored = await cache_get(key)
    
    # Cast both to string and strip to handle Pydantic int-coercion or accidental whitespace
    if stored is not None and str(stored).strip() == str(answer).strip():
        await cache_delete(key)
        return True

    log.warning("auth.captcha_mismatch", captcha_id=captcha_id, provided=answer, stored_exists=stored is not None)
    return False


def _build_tokens(user: dict) -> dict:
    user_id = str(user["_id"])
    return {
        "access_token": create_access_token(user_id, {"role": user.get("role", "user")}),
        "refresh_token": create_refresh_token(user_id),
        "token_type": "bearer",
        "user_id": user_id,
        "role": user.get("role", "user"),
    }
