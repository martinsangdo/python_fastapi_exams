"""
app/worker.py

Celery async task queue — Module 3 (Queue message / async tasks).

Tasks:
  - send_results_email  : email user their test results
  - update_analytics    : recalculate exam pass-rate after attempt
  - process_payment     : delayed payment fulfillment retry

Run: celery -A app.worker worker --loglevel=info
"""
from celery import Celery
import structlog

from app.core.config import settings

log = structlog.get_logger()

celery_app = Celery(
    "examprep",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.worker"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_max_tasks_per_child=1000,
)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_results_email(self, user_email: str, exam_title: str, score: float, passed: bool):
    """
    Send exam results email to the user.
    Retries up to 3 times on failure (Module 2: resilience).
    """
    try:
        log.info("email.send", to=user_email, exam=exam_title, score=score, passed=passed)
        # In production: use SendGrid / AWS SES
        # import sendgrid
        # sg = sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
        # message = Mail(
        #     from_email="noreply@examprep.dev",
        #     to_emails=user_email,
        #     subject=f"Your {exam_title} results",
        #     html_content=render_results_email(exam_title, score, passed),
        # )
        # sg.send(message)
        log.info("email.sent", to=user_email)
        return {"status": "sent", "to": user_email}
    except Exception as exc:
        log.error("email.failed", error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task
def recalculate_exam_stats(exam_id: str):
    """
    Recompute exam-level aggregate stats after an attempt completes.
    Runs async so it doesn't block the HTTP response.
    """
    import asyncio
    from app.core.database import connect_db, close_db, get_db

    async def _run():
        await connect_db()
        db = get_db()
        from bson import ObjectId
        pipeline = [
            {"$match": {"exam_id": exam_id, "status": "completed"}},
            {"$group": {
                "_id": None,
                "total": {"$sum": 1},
                "passed": {"$sum": {"$cond": ["$passed", 1, 0]}},
                "avg_score": {"$avg": "$score"},
            }},
        ]
        async for row in db.attempts.aggregate(pipeline):
            pass_rate = round(row["passed"] / row["total"] * 100, 1) if row["total"] else 0
            await db.exams.update_one(
                {"_id": ObjectId(exam_id)},
                {"$set": {"avg_pass_rate": pass_rate}},
            )
        await close_db()

    asyncio.run(_run())
    log.info("exam.stats_updated", exam_id=exam_id)


@celery_app.task(bind=True, max_retries=5, default_retry_delay=30)
def process_payment_webhook(self, payload: dict):
    """
    Async payment processing — handles Stripe webhook retries.
    Module 2: Idempotency + retry pattern.
    """
    import asyncio
    from app.core.database import connect_db, close_db

    async def _run():
        await connect_db()
        from app.services.payment_service import fulfill_purchase
        await fulfill_purchase(
            user_id=payload["user_id"],
            exam_id=payload["exam_id"],
            amount_usd=payload["amount_usd"],
            payment_id=payload["payment_id"],
        )
        await close_db()

    try:
        asyncio.run(_run())
        return {"status": "fulfilled"}
    except Exception as exc:
        log.error("payment.task_failed", error=str(exc))
        raise self.retry(exc=exc)


# Periodic task: daily DB backup notification (Module 3: scheduled jobs)
@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Run analytics refresh every hour
    sender.add_periodic_task(3600.0, refresh_all_analytics.s(), name="hourly-analytics")


@celery_app.task
def refresh_all_analytics():
    """Triggered hourly to keep aggregate stats fresh."""
    log.info("analytics.refresh_start")
    # In production: iterate all exams and queue recalculate_exam_stats
    return {"status": "ok"}
