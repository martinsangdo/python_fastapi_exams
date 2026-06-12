"""
app/services/contact_service.py — Contact inquiry business logic
"""
from datetime import datetime, timezone, timedelta

from app.core.database import get_db
from app.models.documents import new_contact_inquiry
from app.schemas.schemas import ContactRequest


# 1 submission per email per calendar day (UTC)
MAX_PER_EMAIL_PER_DAY = 1


async def submit_inquiry(data: ContactRequest, ip: str) -> dict:
    db = get_db()
    email = data.email.lower().strip()

    # Day window in UTC
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    count = await db.contact_inquiries.count_documents({
        "email": email,
        "created_at": {"$gte": day_start, "$lt": day_end},
    })

    if count >= MAX_PER_EMAIL_PER_DAY:
        return {"limited": True}

    doc = new_contact_inquiry(
        name=data.name,
        email=email,
        subject=data.subject,
        message=data.message,
        ip=ip,
    )
    await db.contact_inquiries.insert_one(doc)
    return {"limited": False}
