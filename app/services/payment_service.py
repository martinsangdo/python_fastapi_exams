"""
app/services/payment_service.py

Payment processing via Stripe — Module 2 (Solutions Architect).

Architecture decisions:
  - Idempotency keys prevent double-charges on network retry
  - Webhook signature verification (OWASP: don't trust client data)
  - Purchase check cached in Redis to avoid DB hit on every exam load
  - Exponential backoff on Stripe API calls
"""
import asyncio
import hashlib
from typing import Optional
import structlog

from app.core.database import get_db
from app.core.cache import cache_get, cache_set, cache_delete, CacheKeys
from app.core.config import settings
from app.models.documents import new_purchase

log = structlog.get_logger()


async def create_checkout_session(user_id: str, exam_id: str) -> dict:
    """
    Create a Stripe Checkout session.
    Returns a redirect URL for the client.
    """
    db = get_db()
    from bson import ObjectId

    # Verify exam exists
    exam = await db.exams.find_one({"_id": ObjectId(exam_id)})
    if not exam:
        raise ValueError("Exam not found")

    # Check if already purchased
    if await has_access(user_id, exam_id):
        raise ValueError("You already have access to this exam")

    # Idempotency key: same user+exam always gets same session
    idempotency_key = hashlib.sha256(f"{user_id}:{exam_id}".encode()).hexdigest()

    # In production, call Stripe API:
    # import stripe
    # stripe.api_key = settings.STRIPE_SECRET_KEY
    # session = stripe.checkout.Session.create(
    #     payment_method_types=["card"],
    #     line_items=[{
    #         "price_data": {
    #             "currency": "usd",
    #             "product_data": {"name": exam["title"]},
    #             "unit_amount": int(exam["price_usd"] * 100),
    #         },
    #         "quantity": 1,
    #     }],
    #     mode="payment",
    #     success_url=f"{settings.FRONTEND_URL}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
    #     cancel_url=f"{settings.FRONTEND_URL}/payment/cancel",
    #     metadata={"user_id": user_id, "exam_id": exam_id},
    #     idempotency_key=idempotency_key,
    # )
    # return {"checkout_url": session.url, "session_id": session.id}

    # Demo response (replace with real Stripe call above)
    mock_session_id = f"cs_demo_{idempotency_key[:16]}"
    return {
        "checkout_url": f"https://checkout.stripe.com/pay/{mock_session_id}",
        "session_id": mock_session_id,
    }


async def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """
    Process Stripe webhook events.
    Signature verification prevents fake webhook calls (OWASP Module 2).
    """
    # In production:
    # import stripe
    # event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    #
    # if event["type"] == "checkout.session.completed":
    #     session = event["data"]["object"]
    #     await _fulfill_purchase(
    #         user_id=session["metadata"]["user_id"],
    #         exam_id=session["metadata"]["exam_id"],
    #         amount_usd=session["amount_total"] / 100,
    #         payment_id=session["payment_intent"],
    #     )
    #
    # return {"received": True}

    return {"received": True}


async def fulfill_purchase(user_id: str, exam_id: str, amount_usd: float, payment_id: str) -> dict:
    """
    Record a completed purchase. Idempotent — safe to call multiple times.
    """
    db = get_db()

    # Idempotency check — unique index on stripe_payment_id handles concurrent calls
    existing = await db.purchases.find_one({"stripe_payment_id": payment_id})
    if existing:
        log.info("payment.duplicate_webhook", payment_id=payment_id)
        return _serialize(existing)

    doc = new_purchase(
        user_id=user_id,
        exam_id=exam_id,
        amount_usd=amount_usd,
        stripe_payment_id=payment_id,
        status="completed",
    )
    result = await db.purchases.insert_one(doc)
    doc["_id"] = result.inserted_id

    # Update user stats
    from bson import ObjectId
    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$inc": {"stats.exams_purchased": 1}},
    )

    # Invalidate user purchase cache
    await cache_delete(CacheKeys.USER_PURCHASES.format(user_id=user_id))

    log.info("payment.fulfilled", user_id=user_id, exam_id=exam_id, amount=amount_usd)
    return _serialize(doc)


async def has_access(user_id: str, exam_id: str) -> bool:
    """
    Check if a user has purchased an exam.
    Cached to avoid DB hit on every API call.
    """
    cache_key = f"access:{user_id}:{exam_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    db = get_db()
    purchase = await db.purchases.find_one({
        "user_id": user_id,
        "exam_id": exam_id,
        "status": "completed",
    })
    result = purchase is not None
    await cache_set(cache_key, result, ttl=300)
    return result


async def list_user_purchases(user_id: str) -> list[dict]:
    cache_key = CacheKeys.USER_PURCHASES.format(user_id=user_id)
    cached = await cache_get(cache_key)
    if cached:
        return cached

    db = get_db()
    cursor = db.purchases.find({"user_id": user_id, "status": "completed"}).sort("purchased_at", -1)
    purchases = [_serialize(p) async for p in cursor]
    await cache_set(cache_key, purchases, ttl=120)
    return purchases


async def _retry_with_backoff(coro, retries=3, base_delay=1.0):
    """
    Exponential backoff for external API calls (Module 2: Solutions Architect).
    Prevents overwhelming a recovering service.
    """
    for attempt in range(retries):
        try:
            return await coro
        except Exception as e:
            if attempt == retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            log.warning("retry.backoff", attempt=attempt + 1, delay=delay, error=str(e))
            await asyncio.sleep(delay)


def _serialize(doc: dict) -> dict:
    result = dict(doc)
    result["id"] = str(result.pop("_id"))
    return result
