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


_LOGIN_FAIL_LIMIT = 10       # max failed attempts per email per hour
_LOGIN_FAIL_WINDOW = 3600   # seconds


async def login_user(data: LoginRequest, client_ip: str = "unknown") -> dict:
    db = get_db()
    from datetime import timedelta

    email = data.email.lower()

    # Check per-email failed-attempt limit (credential stuffing / brute-force)
    window_start = datetime.now(timezone.utc) - timedelta(seconds=_LOGIN_FAIL_WINDOW)
    fail_count = await db.pw_reset_rate_limits.count_documents({
        "key": f"login_fail:{email}",
        "created_at": {"$gte": window_start},
    })
    if fail_count >= _LOGIN_FAIL_LIMIT:
        log.warning("auth.login.brute_force", email=email, ip=client_ip)
        raise AuthError("Too many failed attempts. Please try again in an hour or reset your password.", 429)

    user = await db.users.find_one({"email": email})

    if not user or not verify_password(data.password, user["hashed_password"]):
        # Record failed attempt
        now = datetime.now(timezone.utc)
        await db.pw_reset_rate_limits.insert_one({
            "key": f"login_fail:{email}",
            "created_at": now,
            "expires_at": now + timedelta(seconds=_LOGIN_FAIL_WINDOW),
        })
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


_RESET_TTL_SECONDS = 15 * 60  # 15 minutes
_RATE_WINDOW_SECONDS = 3600   # 1 hour
_RATE_LIMIT_PER_EMAIL = 3
_RATE_LIMIT_PER_IP = 10


async def forgot_password(email: str, client_ip: str) -> None:
    """
    Generate a signed reset token and send it via Resend.
    Always returns without error to avoid user enumeration.
    Rate-limited by IP and email via MongoDB TTL collection.
    """
    db = get_db()
    from datetime import timedelta

    # Rate limit by IP
    ip_count = await db.pw_reset_rate_limits.count_documents({
        "key": f"ip:{client_ip}",
        "created_at": {"$gte": datetime.now(timezone.utc) - timedelta(seconds=_RATE_WINDOW_SECONDS)},
    })
    if ip_count >= _RATE_LIMIT_PER_IP:
        log.warning("auth.forgot_password.rate_limit_ip", ip=client_ip)
        return

    # Rate limit by email
    email_count = await db.pw_reset_rate_limits.count_documents({
        "key": f"email:{email.lower()}",
        "created_at": {"$gte": datetime.now(timezone.utc) - timedelta(seconds=_RATE_WINDOW_SECONDS)},
    })
    if email_count >= _RATE_LIMIT_PER_EMAIL:
        log.warning("auth.forgot_password.rate_limit_email", email=email)
        return

    user = await db.users.find_one({"email": email.lower()})

    # Record attempt regardless of whether user exists (prevents timing-based enumeration)
    now = datetime.now(timezone.utc)
    await db.pw_reset_rate_limits.insert_one({
        "key": f"ip:{client_ip}",
        "created_at": now,
        "expires_at": now + timedelta(seconds=_RATE_WINDOW_SECONDS),
    })
    await db.pw_reset_rate_limits.insert_one({
        "key": f"email:{email.lower()}",
        "created_at": now,
        "expires_at": now + timedelta(seconds=_RATE_WINDOW_SECONDS),
    })

    if not user:
        return  # silent — don't reveal whether email is registered

    # Stateless HMAC token: signed with SECRET_KEY + current password hash slice
    # Automatically invalidated when the password changes
    import hmac, hashlib
    signing_key = settings.SECRET_KEY + user["hashed_password"][:16]
    user_id = str(user["_id"])
    expires_at = int((now + timedelta(seconds=_RESET_TTL_SECONDS)).timestamp())
    payload = f"{user_id}:{expires_at}"
    sig = hmac.new(signing_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    token = f"{payload}:{sig}"

    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    await _send_reset_email(email, user.get("username", "there"), reset_url)
    log.info("auth.forgot_password.sent", user_id=user_id)


async def reset_password(token: str, new_password: str) -> None:
    """Validate the HMAC token and update the user's password."""
    import hmac, hashlib, time
    from bson import ObjectId

    parts = token.split(":")
    if len(parts) != 3:
        raise AuthError("Invalid or expired reset link", 400)

    user_id, expires_at_str, sig = parts
    try:
        expires_at = int(expires_at_str)
    except ValueError:
        raise AuthError("Invalid or expired reset link", 400)

    if time.time() > expires_at:
        raise AuthError("Reset link has expired. Please request a new one.", 400)

    db = get_db()
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise AuthError("Invalid or expired reset link", 400)

    signing_key = settings.SECRET_KEY + user["hashed_password"][:16]
    payload = f"{user_id}:{expires_at_str}"
    expected_sig = hmac.new(signing_key.encode(), payload.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(sig, expected_sig):
        raise AuthError("Invalid or expired reset link", 400)

    new_hash = hash_password(new_password)
    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"hashed_password": new_hash}},
    )
    log.info("auth.reset_password.success", user_id=user_id)


async def _send_reset_email(to_email: str, username: str, reset_url: str) -> None:
    if not settings.RESEND_API_KEY:
        log.error("auth.reset_email.no_api_key")
        raise AuthError("Email service is not configured", 500)

    import resend
    import asyncio
    resend.api_key = settings.RESEND_API_KEY
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto">
      <h2 style="color:#1a1a2e">Reset your password</h2>
      <p>Hi {username},</p>
      <p>We received a request to reset your CertQuestionBank password.
         Click the button below — this link expires in <strong>15 minutes</strong>.</p>
      <a href="{reset_url}"
         style="display:inline-block;padding:12px 24px;background:#7c3aed;color:#fff;
                border-radius:8px;text-decoration:none;font-weight:600;margin:16px 0">
        Reset Password
      </a>
      <p style="color:#666;font-size:.875rem">
        If you didn't request this, you can safely ignore this email.<br/>
        This link will expire in 15 minutes.
      </p>
    </div>
    """
    try:
        result = await asyncio.to_thread(resend.Emails.send, {
            "from": settings.EMAIL_FROM,
            "to": [to_email],
            "subject": "Reset your CertQuestionBank password",
            "html": html,
        })
        log.info("auth.reset_email.sent", to=to_email, result=result)
    except Exception as e:
        log.error("auth.reset_email.failed", to=to_email, error=str(e))
        raise AuthError("Failed to send reset email. Please try again later.", 500)


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
