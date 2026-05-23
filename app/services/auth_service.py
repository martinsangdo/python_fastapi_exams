"""
app/services/auth_service.py

Authentication business logic — Module 1 (FastAPI MVC) + Module 2 (Security).
- Register with email uniqueness check
- Login with bcrypt verification
- JWT access + refresh token pair
- Token refresh and logout (blacklist)
"""
from datetime import datetime, timezone
from typing import Optional
import structlog

from app.core.database import get_db
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


async def register_user(data: RegisterRequest) -> dict:
    db = get_db()

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


def _build_tokens(user: dict) -> dict:
    user_id = str(user["_id"])
    return {
        "access_token": create_access_token(user_id, {"role": user.get("role", "user")}),
        "refresh_token": create_refresh_token(user_id),
        "token_type": "bearer",
        "user_id": user_id,
        "role": user.get("role", "user"),
    }
