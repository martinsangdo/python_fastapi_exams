"""
app/services/attempt_service.py

Test attempt lifecycle:
  start → submit answers progressively → finish → get results

DSA used: Hash map for O(1) question lookup during grading.
Module 2: Cache for in-progress attempt state (reduces DB writes per answer).
"""
from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId
import structlog

from app.core.database import get_db
from app.core.cache import cache_get, cache_set, cache_delete, get_cache
from app.models.documents import new_attempt, new_answer, utcnow
from app.utils.dsa import QuestionCache, calculate_score

log = structlog.get_logger()

# Prefix for in-progress attempt state stored in Redis
_ATTEMPT_STATE_PREFIX = "attempt_state:"
_ATTEMPT_STATE_TTL = 7200  # 2 hours — longer than any exam


async def start_attempt(user_id: str, package_id: str, exam_id: str = "") -> dict:
    db = get_db()

    # Support both ObjectId packages (db.packages) and cert-based pkg-{n} packages
    if package_id.startswith("pkg-"):
        if not exam_id:
            raise ValueError("exam_id required for cert-based packages")
        from app.services.exam_service import _find_cert_metadata
        pkg_order = int(package_id.split("-")[1])
        meta = await _find_cert_metadata(exam_id)
        question_count = 0
        if meta and meta.get("collection_name"):
            question_count = await db[meta["collection_name"]].count_documents({"package": pkg_order})
        pass_score_pct = (meta or {}).get("pass_score_pct", 72)
        package = {"exam_id": exam_id, "question_count": question_count, "pass_score_pct": pass_score_pct}
    else:
        package = await db.packages.find_one({"_id": ObjectId(package_id)})
        if not package:
            raise ValueError("Package not found")
        exam_id = package["exam_id"]

    purchase = await db.purchases.find_one({
        "user_id": user_id,
        "exam_id": exam_id,
        "status": "completed",
    })
    if not purchase:
        raise PermissionError("Access denied — please purchase this exam first")

    # Prevent multiple in-progress attempts on same package
    existing = await db.attempts.find_one({
        "user_id": user_id,
        "package_id": package_id,
        "status": "in_progress",
    })
    if existing:
        return _serialize(existing)   # resume existing attempt

    doc = new_attempt(user_id=user_id, package_id=package_id, exam_id=exam_id)
    doc["total_questions"] = package["question_count"]
    result = await db.attempts.insert_one(doc)
    doc["_id"] = result.inserted_id

    log.info("attempt.started", attempt_id=str(result.inserted_id), user_id=user_id)
    return _serialize(doc)


async def submit_answer(attempt_id: str, user_id: str, question_id: str,
                        selected_keys: list[str], time_seconds: int = 0) -> dict:
    """
    Validate and record one answer.
    O(1) question lookup from Redis cache (Module 1: Hash map, Module 2: Cache).
    """
    db = get_db()
    attempt = await db.attempts.find_one({"_id": ObjectId(attempt_id), "user_id": user_id})
    if not attempt:
        raise ValueError("Attempt not found")
    if attempt["status"] != "in_progress":
        raise ValueError("Attempt is already completed")

    # Check if question already answered
    answered_ids = {a["question_id"] for a in attempt.get("answers", [])}
    if question_id in answered_ids:
        raise ValueError("Question already answered")

    # O(1) lookup from cache
    question = await _get_question_from_cache(attempt["package_id"], question_id)
    if not question:
        # Cache miss fallback — O(log n) index lookup
        question = await db.questions.find_one({"_id": ObjectId(question_id)})
        if not question:
            raise ValueError("Question not found")

    correct_keys = {o["key"] for o in question["options"] if o["is_correct"]}
    is_correct = set(selected_keys) == correct_keys

    answer = new_answer(question_id, selected_keys, is_correct, time_seconds)

    await db.attempts.update_one(
        {"_id": ObjectId(attempt_id)},
        {
            "$push": {"answers": answer},
            "$inc": {"correct_count": 1 if is_correct else 0},
        },
    )

    # Update question analytics
    await db.questions.update_one(
        {"_id": ObjectId(question_id)},
        {"$inc": {"times_answered": 1, "times_correct": 1 if is_correct else 0}},
    )

    return {
        "is_correct": is_correct,
        "correct_keys": list(correct_keys),
        "explanation": question.get("explanation", ""),
    }


async def finish_attempt(attempt_id: str, user_id: str, correct_count: int = None, total_questions: int = None) -> dict:
    """Calculate final score, mark attempt complete, update user stats."""
    db = get_db()
    attempt = await db.attempts.find_one({"_id": ObjectId(attempt_id), "user_id": user_id})
    if not attempt:
        raise ValueError("Attempt not found")
    if attempt["status"] != "in_progress":
        raise ValueError("Attempt is already completed")

    pkg_id = attempt["package_id"]
    if pkg_id.startswith("pkg-"):
        package = {"question_count": attempt.get("total_questions", 0), "pass_score_pct": 72}
    else:
        package = await db.packages.find_one({"_id": ObjectId(pkg_id)}) or {}
    total = total_questions if total_questions is not None else (attempt.get("total_questions") or package.get("question_count", 0))
    correct = correct_count if correct_count is not None else attempt.get("correct_count", 0)
    score = calculate_score(correct, total)
    passed = score >= package.get("pass_score_pct", 72)
    completed_at = utcnow()

    # Calculate time spent
    started = attempt["started_at"]
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    time_spent = int((completed_at - started).total_seconds())

    await db.attempts.update_one(
        {"_id": ObjectId(attempt_id)},
        {"$set": {
            "status": "completed",
            "score": score,
            "passed": passed,
            "time_spent_seconds": time_spent,
            "completed_at": completed_at,
        }},
    )

    # Update user stats (denormalized)
    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$inc": {
            "stats.total_attempts": 1,
            "stats.total_correct": correct,
        }},
    )

    # Update exam avg pass rate
    await _update_exam_pass_rate(attempt["exam_id"])

    # Cleanup attempt cache
    cache = get_cache()
    await cache.delete(f"{_ATTEMPT_STATE_PREFIX}{attempt['package_id']}")

    log.info("attempt.completed", attempt_id=attempt_id, score=score, passed=passed)

    # Build results with explanations (only for db.questions-based packages)
    answers_with_detail = []
    if not attempt["package_id"].startswith("pkg-"):
        for ans in attempt.get("answers", []):
            try:
                q = await db.questions.find_one({"_id": ObjectId(ans["question_id"])})
            except Exception:
                q = None
            correct_keys = [o["key"] for o in q["options"] if o["is_correct"]] if q else []
            answers_with_detail.append({
                "question_id": ans["question_id"],
                "selected_keys": ans["selected_keys"],
                "correct_keys": correct_keys,
                "is_correct": ans["is_correct"],
                "explanation": q.get("explanation", "") if q else "",
            })

    return {
        "attempt_id": attempt_id,
        "score": score,
        "correct_count": correct,
        "total_questions": total,
        "passed": passed,
        "time_spent_seconds": time_spent,
        "answers": answers_with_detail,
        "pass_score_pct": package["pass_score_pct"],
    }


async def get_user_attempts(user_id: str, page: int = 1, page_size: int = 20) -> dict:
    db = get_db()
    query = {"user_id": user_id, "status": "completed"}
    total = await db.attempts.count_documents(query)
    skip = (page - 1) * page_size
    cursor = db.attempts.find(query).sort("completed_at", -1).skip(skip).limit(page_size)
    items = [_serialize(a) async for a in cursor]
    return {"items": items, "total": total, "page": page}


# ─── Private helpers ──────────────────────────────────────────────────────────

async def _preload_questions_to_cache(package_id: str):
    """Load all questions for a package into Redis as individual keys (hash map)."""
    db = get_db()
    cache = get_cache()
    async for q in db.questions.find({"package_id": package_id}):
        key = f"q:{package_id}:{str(q['_id'])}"
        import json
        q["_id"] = str(q["_id"])
        await cache.setex(key, _ATTEMPT_STATE_TTL, json.dumps(q, default=str))


async def _get_question_from_cache(package_id: str, question_id: str) -> Optional[dict]:
    """O(1) hash map lookup from Redis."""
    cache = get_cache()
    import json
    raw = await cache.get(f"q:{package_id}:{question_id}")
    return json.loads(raw) if raw else None


async def _update_exam_pass_rate(exam_id: str):
    db = get_db()
    pipeline = [
        {"$match": {"exam_id": exam_id, "status": "completed"}},
        {"$group": {
            "_id": None,
            "pass_count": {"$sum": {"$cond": ["$passed", 1, 0]}},
            "total": {"$sum": 1},
        }},
    ]
    async for row in db.attempts.aggregate(pipeline):
        if row["total"] > 0:
            avg = round(row["pass_count"] / row["total"] * 100, 1)
            await db.exams.update_one(
                {"_id": ObjectId(exam_id)},
                {"$set": {"avg_pass_rate": avg}},
            )


def _serialize(doc: dict) -> dict:
    result = dict(doc)
    result["id"] = str(result.pop("_id"))
    return result
