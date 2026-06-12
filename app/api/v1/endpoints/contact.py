"""
app/api/v1/endpoints/contact.py — Contact inquiry endpoint
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.middleware.auth import rate_limit
from app.schemas.schemas import ContactRequest, OkResponse
from app.services import contact_service
from app.services.auth_service import _verify_captcha

router = APIRouter(prefix="/contact", tags=["Contact"])

# 5 attempts per IP per minute at the HTTP layer (backs the email-per-day check)
_ip_limiter = rate_limit


@router.post("", response_model=OkResponse, status_code=201)
async def submit_contact(
    data: ContactRequest,
    request: Request,
    _=Depends(_ip_limiter),
):
    if not await _verify_captcha(data.captcha_id, data.captcha_answer):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired captcha.")
    ip = request.client.host if request.client else "unknown"
    result = await contact_service.submit_inquiry(data, ip)
    if result["limited"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You have already submitted a contact request today. Please try again tomorrow.",
        )
    return OkResponse(message="Your message has been received. We'll get back to you soon.")
