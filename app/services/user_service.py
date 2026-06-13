"""
app/services/user_service.py

User profile and admin user management service.
"""
from typing import Optional
from bson import ObjectId
import structlog

from app.core.database import get_db
from app.core.security import hash_password
from app.models.documents import utcnow

log = structlog.get_logger()


async def get_user_by_id(user_id: str) -> Optional[dict]:
    db = get_db()
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    return _serialize(user) if user else None


async def update_profile(user_id: str, full_name: str = None, avatar_url: str = None, bio: str = None) -> Optional[dict]:
    db = get_db()
    updates = {"updated_at": utcnow()}
    if full_name is not None:
        updates["profile.full_name"] = full_name
    if avatar_url is not None:
        updates["profile.avatar_url"] = avatar_url
    if bio is not None:
        updates["profile.bio"] = bio

    user = await db.users.find_one_and_update(
        {"_id": ObjectId(user_id)},
        {"$set": updates},
        return_document=True,
    )
    return _serialize(user) if user else None


async def change_password(user_id: str, new_password: str) -> bool:
    db = get_db()
    result = await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"hashed_password": hash_password(new_password), "updated_at": utcnow()}},
    )
    return result.modified_count > 0


async def list_users(page: int = 1, page_size: int = 20) -> dict:
    """Admin: paginated user list."""
    db = get_db()
    total = await db.users.count_documents({})
    skip = (page - 1) * page_size
    cursor = db.users.find({}, {"hashed_password": 0}).sort("created_at", -1).skip(skip).limit(page_size)
    items = [_serialize(u) async for u in cursor]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def set_user_active(user_id: str, is_active: bool) -> bool:
    """Admin: activate / deactivate a user account."""
    db = get_db()
    result = await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"is_active": is_active, "updated_at": utcnow()}},
    )
    return result.modified_count > 0


async def get_user_dashboard_stats(user_id: str) -> dict:
    """
    Aggregate stats for a user's profile dashboard.
    Uses MongoDB aggregation pipeline for efficiency.
    """
    db = get_db()

    # Attempts stats
    pipeline = [
        {"$match": {"user_id": user_id, "status": "completed"}},
        {"$group": {
            "_id": None,
            "total_attempts": {"$sum": 1},
            "passed_count":   {"$sum": {"$cond": ["$passed", 1, 0]}},
            "avg_score":      {"$avg": "$score"},
            "best_score":     {"$max": "$score"},
        }},
    ]
    stats = {"total_attempts": 0, "passed_count": 0, "avg_score": 0.0, "best_score": 0.0}
    async for row in db.attempts.aggregate(pipeline):
        stats = {
            "total_attempts": row["total_attempts"],
            "passed_count":   row["passed_count"],
            "avg_score":      round(row["avg_score"], 1),
            "best_score":     round(row["best_score"], 1),
        }

    # Purchases count
    purchases = await db.purchases.count_documents({"user_id": user_id, "status": "completed"})

    # Recent attempts
    cursor = db.attempts.find({"user_id": user_id, "status": "completed"}).sort("completed_at", -1).limit(5)
    recent = []
    async for a in cursor:
        exam = await db.exams.find_one({"_id": ObjectId(a["exam_id"])}, {"title": 1, "slug": 1})
        pkg  = await db.packages.find_one({"_id": ObjectId(a["package_id"])}, {"title": 1, "order": 1})
        recent.append({
            "attempt_id": str(a["_id"]),
            "exam_title": exam["title"] if exam else "Unknown",
            "exam_slug":  exam["slug"]  if exam else "",
            "pkg_title":  pkg["title"]  if pkg  else "Unknown",
            "score":      a.get("score", 0),
            "passed":     a.get("passed", False),
            "completed_at": a.get("completed_at"),
        })

    return {
        **stats,
        "exams_purchased": purchases,
        "recent_attempts": recent,
    }


def _serialize(doc: Optional[dict]) -> Optional[dict]:
    if doc is None:
        return None
    result = dict(doc)
    result["id"] = str(result.pop("_id"))
    result.pop("hashed_password", None)   # never expose hash
    return result
