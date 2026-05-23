"""
app/api/v1/endpoints/auth.py — Authentication routes
"""
from fastapi import APIRouter, Depends, HTTPException
from app.schemas.schemas import RegisterRequest, LoginRequest, RefreshRequest, TokenResponse, OkResponse
from app.services import auth_service
from app.middleware.auth import get_current_user, rate_limit

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.get("/captcha")
async def get_captcha():
    return await auth_service.generate_captcha()


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(data: RegisterRequest, _=Depends(rate_limit)):
    try:
        return await auth_service.register_user(data)
    except auth_service.AuthError as e:
        raise HTTPException(e.status_code, e.message)


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, _=Depends(rate_limit)):
    try:
        return await auth_service.login_user(data)
    except auth_service.AuthError as e:
        raise HTTPException(e.status_code, e.message)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest):
    try:
        return await auth_service.refresh_tokens(data.refresh_token)
    except auth_service.AuthError as e:
        raise HTTPException(e.status_code, e.message)


@router.post("/logout", response_model=OkResponse)
async def logout(data: RefreshRequest, current_user=Depends(get_current_user)):
    from fastapi import Request
    await auth_service.logout_user(
        access_token="",
        refresh_token=data.refresh_token
    )
    return OkResponse(message="Logged out successfully")


@router.get("/me")
async def me(current_user=Depends(get_current_user)):
    from bson import ObjectId
    u = current_user
    return {
        "id": str(u["_id"]),
        "email": u["email"],
        "username": u["username"],
        "role": u.get("role", "user"),
        "profile": u.get("profile", {}),
        "stats": u.get("stats", {}),
        "created_at": u.get("created_at"),
    }
