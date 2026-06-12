"""
app/services/exam_service.py

Exam + Package + Question business logic.
Demonstrates:
  - Cache-aside pattern (Module 2)
  - DSA: Trie autocomplete, heap leaderboard (Module 1)
  - Denormalized counters (write-through) for fast reads
"""
import math
from typing import Optional
from bson import ObjectId
import structlog

from app.core.database import get_db
from app.core.cache import cache_get, cache_set, cache_delete_pattern, CacheKeys
from app.models.documents import new_exam, new_package, new_question, utcnow
from app.schemas.schemas import ExamCreate, ExamUpdate, PackageCreate, QuestionCreate
from app.utils.dsa import ExamTrie, Leaderboard, count_tag_frequencies

log = structlog.get_logger()

# Module-level Trie — rebuilt on startup, updated on exam create/publish
_exam_trie = ExamTrie()


# ─── Exam CRUD ────────────────────────────────────────────────────────────────

async def create_exam(data: ExamCreate) -> dict:
    db = get_db()
    if await db.exams.find_one({"slug": data.slug}):
        raise ValueError(f"Slug '{data.slug}' already exists")

    doc = new_exam(**data.model_dump())
    result = await db.exams.insert_one(doc)
    doc["_id"] = result.inserted_id
    log.info("exam.created", exam_id=str(result.inserted_id), slug=data.slug)
    return _serialize(doc)


async def list_exams(
    category: Optional[str] = None,
    page: int = 1,
    page_size: int = 12,
    published_only: bool = True,
) -> dict:
    cache_key = CacheKeys.EXAM_LIST.format(
        category=category or "all", page=page
    )
    cached = await cache_get(cache_key)
    if cached:
        return cached

    db = get_db()
    query: dict = {}
    if published_only:
        query["is_published"] = True
    if category:
        query["category"] = category

    total = await db.exams.count_documents(query)
    skip = (page - 1) * page_size
    cursor = db.exams.find(query).sort("created_at", -1).skip(skip).limit(page_size)
    items = [_serialize(e) async for e in cursor]

    result = {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }
    await cache_set(cache_key, result, ttl=120)
    return result


async def get_exam_by_slug(slug: str) -> Optional[dict]:
    cache_key = CacheKeys.EXAM_DETAIL.format(slug=slug)
    cached = await cache_get(cache_key)
    if cached:
        return cached

    db = get_db()
    # 1. Try finding by slug in the metadata table first
    query = {"slug": slug}
    meta = await db.tb_cert_metadata.find_one(query)
    
    # Fallback: if no direct slug match, try matching the slug against the certification name
    if not meta:
        # Replace hyphens with spaces to match against titles/names
        search_name = slug.replace('-', ' ')
        meta = await db.tb_cert_metadata.find_one({"name": {"$regex": f".*{search_name}.*", "$options": "i"}})

    if meta:
        # Use the linked exam ID to get full exam details
        exam_id = meta.get("id")
        exam = await db.exams.find_one({"_id": ObjectId(exam_id)}) if exam_id else None
        
        # Merge metadata and main exam record to ensure fields like 'duration' 
        # and 'disclaimer' (which only exist in metadata) are preserved.
        combined_data = _serialize(meta)
        if exam:
            combined_data.update(_serialize(exam))
        result = _transform_cert(combined_data)
    else:
        # 2. Fallback to direct slug search in the exams collection
        exam = await db.exams.find_one({"slug": slug})
        if not exam:
            return None
        result = _transform_cert(_serialize(exam))

    await cache_set(cache_key, result, ttl=300)
    return result


def _transform_cert(cert: dict) -> dict:
    """Standardize exam/certification object for frontend consumption."""
    category = cert.get("category", "Other")
    # Ensure we capture question count from all possible field names used in different collections
    total_q = cert.get("multi_choice_questions") or cert.get("total_questions") or cert.get("questions", 0)
    
    symbol = cert.get("symbol") or ""
    normalized_symbol = symbol.upper() if isinstance(symbol, str) else ""
    logo_url = cert.get("logo_url") or (normalized_symbol and f"/logos/{normalized_symbol}.png") or ""
    return {
        "id": cert.get("id") or str(cert.get("_id")),
        "slug": cert.get("slug") or "",
        "title": cert.get("name") or cert.get("title") or "Untitled",
        "category": category,
        "description": cert.get("short_brief") or cert.get("description") or "",
        "price": cert.get("price_usd") or cert.get("price") or 29.99,
        "students": cert.get("students", 0),
        "questions": total_q,
        "learns": cert.get("what_learn") or cert.get("learns") or [],
        "requirements": cert.get("requirements") or [],
        "duration": cert.get("duration") or cert.get("time_limit_minutes") or 0,
        "disclaimer": cert.get("disclaimer", ""),
        "avg_pass_rate": cert.get("avg_pass_rate"),
        "symbol": normalized_symbol,
        "logo_url": logo_url,
    }


async def _find_cert_metadata(exam_id: str) -> Optional[dict]:
    db = get_db()
    meta = None
    try:
        meta = await db.tb_cert_metadata.find_one({"_id": ObjectId(exam_id)})
    except Exception:
        pass
    if meta:
        return meta
    return await db.tb_cert_metadata.find_one({"id": exam_id})


def _package_order_from_id(package_id: str) -> Optional[int]:
    if not package_id:
        return None
    if package_id.startswith("pkg-"):
        try:
            return int(package_id.split("-", 1)[1])
        except ValueError:
            return None
    if package_id.isdigit():
        return int(package_id)
    return None


async def list_cert_categories() -> list[str]:
    cache_key = CacheKeys.CERT_METADATA_CATEGORIES
    cached = await cache_get(cache_key)
    if cached:
        return cached

    db = get_db()
    categories = await db.tb_cert_metadata.distinct("category", {"category": {"$exists": True, "$ne": ""}})
    categories = [c for c in categories if isinstance(c, str)]
    await cache_set(cache_key, categories, ttl=600)
    return categories


async def list_certifications() -> dict:
    """Fetch all certifications from tb_cert_metadata grouped by category."""
    cache_key = CacheKeys.CERT_METADATA_CERTIFICATIONS
    cached = await cache_get(cache_key)
    if cached:
        return cached

    db = get_db()
    cursor = db.tb_cert_metadata.find({})
    certs = [_serialize(c) async for c in cursor]
    
    # Group by category
    by_category = {}
    all_transformed = []
    for cert in certs:
        category = cert.get("category", "Other")
        if category not in by_category:
            by_category[category] = []
        
        cert_display = _transform_cert(cert)
        by_category[category].append(cert_display)
        all_transformed.append(cert_display)
    
    result = {"by_category": by_category, "all": all_transformed}
    await cache_set(cache_key, result, ttl=600)
    return result


async def update_exam(exam_id: str, data: ExamUpdate) -> Optional[dict]:
    db = get_db()
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    updates["updated_at"] = utcnow()

    result = await db.exams.find_one_and_update(
        {"_id": ObjectId(exam_id)},
        {"$set": updates},
        return_document=True,
    )
    if result:
        # Invalidate all cache related to this exam (Module 2: cache invalidation)
        await cache_delete_pattern(f"*{exam_id}*")
        await cache_delete_pattern("exams:list:*")
    return _serialize(result) if result else None


async def autocomplete_exams(prefix: str) -> list[str]:
    """O(m) Trie lookup for search autocomplete — Module 1: DSA."""
    return _exam_trie.search(prefix)


async def rebuild_trie():
    """Called on startup to populate the in-memory Trie."""
    db = get_db()
    async for exam in db.exams.find({"is_published": True}, {"title": 1}):
        _exam_trie.insert(exam["title"], str(exam["_id"]))


# ─── Package CRUD ─────────────────────────────────────────────────────────────

async def create_package(exam_id: str, data: PackageCreate) -> dict:
    db = get_db()
    exam = await db.exams.find_one({"_id": ObjectId(exam_id)})
    if not exam:
        raise ValueError("Exam not found")
    if await db.packages.count_documents({"exam_id": exam_id}) >= 6:
        raise ValueError("An exam can have at most 6 packages")

    doc = new_package(exam_id=exam_id, **data.model_dump())
    result = await db.packages.insert_one(doc)
    doc["_id"] = result.inserted_id
    await cache_delete_pattern(f"packages:exam:{exam_id}")
    return _serialize(doc)


async def list_packages(exam_id: str) -> list[dict]:
    cache_key = CacheKeys.PACKAGE_LIST.format(exam_id=exam_id)
    cached = await cache_get(cache_key)
    if cached:
        return cached

    db = get_db()
    meta = await _find_cert_metadata(exam_id)
    packages = []

    if meta and meta.get("collection_name"):
        collection = db[meta["collection_name"]]
        pipeline = [
            {"$match": {"package": {"$exists": True}}},
            {"$group": {"_id": "$package", "count": {"$sum": 1}}},
        ]

        counts = {}
        async for row in collection.aggregate(pipeline):
            try:
                pkg_num = int(row["_id"])
            except Exception:
                continue
            counts[pkg_num] = row["count"]

        duration = meta.get("duration") or meta.get("time_limit_minutes") or 90
        pass_score_pct = meta.get("pass_score_pct", 72)

        for order in range(1, 7):
            packages.append({
                "id": f"pkg-{order}",
                "exam_id": exam_id,
                "order": order,
                "title": f"Practice Test {order}",
                "description": meta.get("short_brief", ""),
                "time_limit_minutes": duration,
                "pass_score_pct": pass_score_pct,
                "question_count": counts.get(order, 0),
                "is_active": True,
            })
    else:
        cursor = db.packages.find({"exam_id": exam_id}).sort("order", 1)
        async for p in cursor:
            pkg = _serialize(p)
            pkg["duration"] = pkg.get("time_limit_minutes", 0)
            pkg["questions"] = pkg.get("question_count", 0)
            packages.append(pkg)

    await cache_set(cache_key, packages, ttl=300)
    return packages


# ─── Question CRUD ────────────────────────────────────────────────────────────

async def add_question(package_id: str, data: QuestionCreate) -> dict:
    db = get_db()
    package = await db.packages.find_one({"_id": ObjectId(package_id)})
    if not package:
        raise ValueError("Package not found")

    doc = new_question(
        package_id=package_id,
        exam_id=package["exam_id"],
        **data.model_dump(),
    )
    result = await db.questions.insert_one(doc)
    doc["_id"] = result.inserted_id

    # Denormalized counter update (write-through)
    await db.packages.update_one(
        {"_id": ObjectId(package_id)},
        {"$inc": {"question_count": 1}},
    )
    await db.exams.update_one(
        {"_id": ObjectId(package["exam_id"])},
        {"$inc": {"total_questions": 1}},
    )
    await cache_delete_pattern(f"questions:package:{package_id}")
    return _serialize(doc)


async def list_questions_public(exam_id: str, package_id: str) -> list[dict]:
    """Return test questions for a purchased exam package."""
    cache_key = CacheKeys.QUESTION_LIST.format(exam_id=exam_id, package_id=package_id)
    cached = await cache_get(cache_key)
    if cached:
        return cached

    db = get_db()
    meta = await _find_cert_metadata(exam_id)
    questions = []

    if meta and meta.get("collection_name"):
        package_order = _package_order_from_id(package_id)
        if package_order is None:
            return []

        collection = db[meta["collection_name"]]
        cursor = collection.find({"package": package_order})
        async for q in cursor:
            opts = q.get("options", {})
            public_options = []
            if isinstance(opts, dict):
                public_options = [{"key": k, "text": v} for k, v in opts.items()]
            elif isinstance(opts, list):
                public_options = [{"key": o["key"], "text": o["text"]} for o in opts if o.get("key") is not None]

            answer = q.get("answer")
            correct = []
            if isinstance(answer, str) and answer:
                correct = [answer]
            elif isinstance(answer, list):
                correct = [str(a) for a in answer]

            explanation_data = q.get("explanation", "")
            if isinstance(explanation_data, dict):
                explanations = {k: v for k, v in explanation_data.items()}
                explanation_key = answer if isinstance(answer, str) else (",".join(str(a) for a in answer) if isinstance(answer, list) else "")
                explanation = explanation_data.get(explanation_key, "") or " ".join([f"{k}: {v}" for k, v in explanation_data.items()])
            else:
                explanation = explanation_data or ""
                explanations = {}

            # Derive type from correct answer count — DB type field is unreliable
            q_type = "single" if len(correct) <= 1 else "multiple"

            questions.append({
                "id": q.get("uuid") or str(q.get("_id")),
                "text": q.get("question") or q.get("text", ""),
                "type": q_type,
                "options": public_options,
                "correct": correct,
                "explanation": explanation,
                "explanations": explanations,
                "tags": q.get("tags", []),
                "difficulty": q.get("difficulty", "medium"),
            })
    else:
        cursor = db.questions.find({"package_id": package_id})
        async for q in cursor:
            public_options = [{"key": o["key"], "text": o["text"]} for o in q["options"]]
            questions.append({
                "id": str(q["_id"]),
                "text": q["text"],
                "type": q["type"],
                "options": public_options,
                "correct": q.get("correct", []),
                "explanation": q.get("explanation", "") if isinstance(q.get("explanation"), str) else "",
                "explanations": q.get("explanation", {}) if isinstance(q.get("explanation"), dict) else {},
                "tags": q.get("tags", []),
                "difficulty": q.get("difficulty", "medium"),
            })

    await cache_set(cache_key, questions, ttl=604800)  # 7 days
    return questions


PREVIEW_QUESTION_COUNT = 10

async def list_preview_questions(exam_id: str, package_id: str, all_questions: list) -> list:
    """
    Return a stable 5-question preview for package 1 (non-paying users).
    The selection is cached so the same 5 questions are shown on every visit.
    """
    cache_key = f"questions:preview:{exam_id}:{package_id}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    import random
    sample = random.sample(all_questions, min(PREVIEW_QUESTION_COUNT, len(all_questions)))
    await cache_set(cache_key, sample, ttl=604800)  # 7 days
    return sample


async def get_question_with_answers(question_id: str) -> Optional[dict]:
    """Full question with answers — admin + grading only."""
    db = get_db()
    q = await db.questions.find_one({"_id": ObjectId(question_id)})
    return _serialize(q) if q else None


# ─── Leaderboard ──────────────────────────────────────────────────────────────

async def get_leaderboard(exam_id: str, top_n: int = 10) -> list[dict]:
    """
    Build top-N leaderboard using min-heap (DSA Module 1).
    Cached for 60s — slight staleness is acceptable for leaderboard (AHA principle).
    """
    cache_key = CacheKeys.LEADERBOARD.format(exam_id=exam_id, n=top_n)
    cached = await cache_get(cache_key)
    if cached:
        return cached

    db = get_db()
    board = Leaderboard(k=top_n)

    # Aggregate: best score per user per exam
    pipeline = [
        {"$match": {"exam_id": exam_id, "status": "completed"}},
        {"$sort": {"score": -1}},
        {"$group": {
            "_id": "$user_id",
            "best_score": {"$first": "$score"},
            "passed": {"$first": "$passed"},
            "completed_at": {"$first": "$completed_at"},
        }},
    ]
    async for row in db.attempts.aggregate(pipeline):
        user = await db.users.find_one(
            {"_id": ObjectId(row["_id"])}, {"username": 1}
        )
        username = user["username"] if user else "unknown"
        board.add(
            score=row["best_score"],
            username=username,
            meta={"passed": row["passed"], "completed_at": row.get("completed_at")},
        )

    result = board.top_k()
    await cache_set(cache_key, result, ttl=60)
    return result


# ─── Analytics ────────────────────────────────────────────────────────────────

async def get_exam_analytics(exam_id: str) -> dict:
    """Tag frequency + difficulty distribution for an exam."""
    db = get_db()
    questions = [q async for q in db.questions.find({"exam_id": exam_id})]
    tag_freq = count_tag_frequencies(questions)
    difficulty_dist = {"easy": 0, "medium": 0, "hard": 0}
    for q in questions:
        difficulty_dist[q.get("difficulty", "medium")] += 1
    return {
        "total_questions": len(questions),
        "tag_frequencies": tag_freq,
        "difficulty_distribution": difficulty_dist,
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _serialize(doc: Optional[dict]) -> Optional[dict]:
    if doc is None:
        return None
    result = dict(doc)
    result["id"] = str(result.pop("_id"))
    return result


async def get_related_exams(exam_id: str, category: str, limit: int = 4) -> list:
    """Fetch related exams from tb_cert_metadata by category, excluding the current exam."""
    cache_key = f"related:{exam_id}:{category}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    db = get_db()
    query: dict = {"category": category}
    if category:
        query["category"] = category

    cursor = db.tb_cert_metadata.find(query).limit(limit + 1)
    results = []
    async for meta in cursor:
        item = _serialize(meta)
        if item.get("id") == exam_id or str(meta.get("_id")) == exam_id:
            continue
        results.append(_transform_cert(item))
        if len(results) >= limit:
            break

    await cache_set(cache_key, results, ttl=300)
    return results
