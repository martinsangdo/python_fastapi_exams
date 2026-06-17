"""
app/services/payment_service.py

Payment processing via PayPal REST API (Orders v2).

Flow:
  1. POST /payments/checkout  → create PayPal order, return approval_url
  2. User approves on PayPal  → redirected to FRONTEND_URL/payment/success?token=ORDER_ID
  3. POST /payments/capture   → capture the approved order, fulfill purchase
  4. PayPal webhook           → PAYMENT.CAPTURE.COMPLETED as a fallback

Architecture notes:
  - Access token is cached in Redis (TTL = expires_in - 60s) to avoid per-request auth calls
  - Idempotency: duplicate capture attempts are rejected via unique index on paypal_order_id
  - Purchase access is cached in Redis (TTL 5 min) to skip DB on every exam load
"""
import hashlib
from typing import Optional
import structlog
import httpx
from bson import ObjectId

from app.core.config import settings
from app.core.cache import cache_get, cache_set, cache_delete, CacheKeys
from app.core.database import get_db

log = structlog.get_logger()

_PAYPAL_BASE = {
    "sandbox": "https://api-m.sandbox.paypal.com",
    "live": "https://api-m.paypal.com",
}


def _base_url() -> str:
    return _PAYPAL_BASE.get(settings.PAYPAL_MODE, _PAYPAL_BASE["sandbox"])


# ── PayPal auth ───────────────────────────────────────────────────────────────

async def _get_access_token() -> str:
    """Return a cached PayPal OAuth2 access token."""
    cache_key = "paypal:access_token"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_base_url()}/v1/oauth2/token",
            auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

    token = data["access_token"]
    ttl = max(data.get("expires_in", 3600) - 60, 60)
    await cache_set(cache_key, token, ttl=ttl)
    return token


def _auth_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


# ── Create order ──────────────────────────────────────────────────────────────

async def create_checkout_session(user_id: str, exam_id: str) -> dict:
    """
    Create a PayPal order for the given exam.
    Returns approval_url (redirect the user there) and order_id.
    """
    db = get_db()

    exam = await db.exams.find_one({"_id": ObjectId(exam_id)})
    if not exam:
        # Many exams live only in tb_cert_metadata — fall back to that collection
        exam = await db.tb_cert_metadata.find_one({"_id": ObjectId(exam_id)})
    if not exam:
        raise ValueError("Exam not found")

    if await has_access(user_id, exam_id):
        raise ValueError("You already have access to this exam")

    title = exam.get("title") or exam.get("name") or "Exam"
    price = float(exam.get("price_usd") or exam.get("price") or 29.99)

    token = await _get_access_token()
    success_url = f"{settings.FRONTEND_URL}/payment/success"
    cancel_url = f"{settings.FRONTEND_URL}/payment/cancel"

    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": f"{user_id}:{exam_id}",
                "description": title,
                "items": [
                    {
                        "name": title,
                        "quantity": "1",
                        "unit_amount": {"currency_code": "USD", "value": f"{price:.2f}"},
                        "category": "DIGITAL_GOODS",
                    }
                ],
                "amount": {
                    "currency_code": "USD",
                    "value": f"{price:.2f}",
                    "breakdown": {
                        "item_total": {"currency_code": "USD", "value": f"{price:.2f}"}
                    },
                },
            }
        ],
        "application_context": {
            "return_url": success_url,
            "cancel_url": cancel_url,
            "brand_name": settings.APP_NAME,
            "user_action": "PAY_NOW",
        },
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_base_url()}/v2/checkout/orders",
            json=payload,
            headers=_auth_headers(token),
        )
        resp.raise_for_status()
        order = resp.json()

    approval_url = next(
        (link["href"] for link in order.get("links", []) if link["rel"] == "approve"),
        None,
    )
    if not approval_url:
        raise RuntimeError("PayPal did not return an approval URL")

    log.info("paypal.order_created", order_id=order["id"], user_id=user_id, exam_id=exam_id)
    return {"approval_url": approval_url, "order_id": order["id"]}


# ── Capture order ─────────────────────────────────────────────────────────────

async def capture_order(user_id: str, order_id: str) -> dict:
    """
    Capture an approved PayPal order and fulfill the purchase.
    Called from the success redirect endpoint after user approves on PayPal.
    """
    db = get_db()

    # Idempotency guard
    existing = await db.purchases.find_one({"paypal_order_id": order_id, "status": "completed"})
    if existing:
        log.info("paypal.duplicate_capture", order_id=order_id)
        return _serialize(existing)

    token = await _get_access_token()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_base_url()}/v2/checkout/orders/{order_id}/capture",
            headers=_auth_headers(token),
            json={},
        )
        resp.raise_for_status()
        captured = resp.json()

    if captured.get("status") != "COMPLETED":
        raise ValueError(f"PayPal capture status: {captured.get('status')}")

    unit = captured["purchase_units"][0]
    ref_id = unit.get("reference_id", "")          # "{user_id}:{exam_id}"
    capture_info = unit["payments"]["captures"][0]
    amount_usd = float(capture_info["amount"]["value"])

    parts = ref_id.split(":", 1)
    if len(parts) != 2 or parts[0] != user_id:
        raise ValueError("Order does not belong to this user")

    exam_id = parts[1]
    return await fulfill_purchase(user_id, exam_id, amount_usd, order_id)


# ── Fulfill purchase ──────────────────────────────────────────────────────────

async def fulfill_purchase(user_id: str, exam_id: str, amount_usd: float, paypal_order_id: str) -> dict:
    """Record a completed purchase. Idempotent."""
    from app.models.documents import new_purchase

    db = get_db()

    existing = await db.purchases.find_one({"paypal_order_id": paypal_order_id})
    if existing:
        return _serialize(existing)

    doc = new_purchase(
        user_id=user_id,
        exam_id=exam_id,
        amount_usd=amount_usd,
        paypal_order_id=paypal_order_id,
        status="completed",
    )
    result = await db.purchases.insert_one(doc)
    doc["_id"] = result.inserted_id

    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$inc": {"stats.exams_purchased": 1}},
    )

    await cache_delete(CacheKeys.USER_PURCHASES.format(user_id=user_id))
    await cache_delete(f"access:{user_id}:{exam_id}")

    log.info("paypal.purchase_fulfilled", user_id=user_id, exam_id=exam_id, amount=amount_usd)
    return _serialize(doc)


# ── Webhook ───────────────────────────────────────────────────────────────────

async def handle_webhook(payload: bytes, headers: dict) -> dict:
    """
    Process PayPal webhook events (PAYMENT.CAPTURE.COMPLETED).
    Verifies the webhook signature against PAYPAL_WEBHOOK_ID before trusting the payload.

    Verification docs:
      https://developer.paypal.com/api/rest/webhooks/rest/#link-eventtypesbysignature
    """
    import json

    if settings.PAYPAL_WEBHOOK_ID:
        token = await _get_access_token()
        verify_payload = {
            "auth_algo": headers.get("paypal-auth-algo", ""),
            "cert_url": headers.get("paypal-cert-url", ""),
            "transmission_id": headers.get("paypal-transmission-id", ""),
            "transmission_sig": headers.get("paypal-transmission-sig", ""),
            "transmission_time": headers.get("paypal-transmission-time", ""),
            "webhook_id": settings.PAYPAL_WEBHOOK_ID,
            "webhook_event": json.loads(payload),
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_base_url()}/v1/notifications/verify-webhook-signature",
                json=verify_payload,
                headers=_auth_headers(token),
            )
            result = resp.json()
        if result.get("verification_status") != "SUCCESS":
            log.warning("paypal.webhook_verification_failed", status=result.get("verification_status"))
            raise ValueError("Webhook signature verification failed")

    event = json.loads(payload)
    event_type = event.get("event_type", "")

    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        resource = event["resource"]
        order_id = resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id")
        amount_usd = float(resource["amount"]["value"])

        # Resolve user/exam from purchase_units reference_id stored at order creation
        if order_id:
            token = await _get_access_token()
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{_base_url()}/v2/checkout/orders/{order_id}",
                    headers=_auth_headers(token),
                )
                order_data = resp.json()
            ref_id = order_data["purchase_units"][0].get("reference_id", "")
            parts = ref_id.split(":", 1)
            if len(parts) == 2:
                user_id, exam_id = parts
                await fulfill_purchase(user_id, exam_id, amount_usd, order_id)
                log.info("paypal.webhook_fulfilled", order_id=order_id)

    return {"received": True}


# ── Access check ──────────────────────────────────────────────────────────────

async def has_access(user_id: str, exam_id: str) -> bool:
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

    # Enrich each purchase with basic exam info so the frontend doesn't need extra lookups
    for p in purchases:
        try:
            exam_oid = ObjectId(p["exam_id"])
            exam = await db.exams.find_one({"_id": exam_oid}, {"title": 1, "slug": 1, "thumbnail_url": 1, "category": 1, "symbol": 1})
            if not exam:
                exam = await db.tb_cert_metadata.find_one({"_id": exam_oid}, {"name": 1, "slug": 1, "logo_url": 1, "category": 1, "symbol": 1})
            if exam:
                symbol = exam.get("symbol") or ""
                logo = f"{settings.CERT_LOGO_BASE_URL}/{symbol}.png" if symbol else ""
                p["exam_title"] = exam.get("title") or exam.get("name")
                p["exam_slug"] = exam.get("slug")
                p["exam_thumbnail"] = logo
                p["exam_category"] = exam.get("category")
        except Exception:
            pass

    await cache_set(cache_key, purchases, ttl=120)
    return purchases


def _serialize(doc: dict) -> dict:
    result = dict(doc)
    result["id"] = str(result.pop("_id"))
    return result
