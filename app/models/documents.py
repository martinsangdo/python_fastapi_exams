"""
app/models/

MongoDB document schemas using plain dicts with Pydantic validation at the API layer.
ODM-style helpers are provided as dataclasses to keep things lightweight.

Collections:
  users        — registered accounts
  exams        — exam products (e.g. "AWS SAA", "PMP")
  packages     — 6 test packages per exam
  questions    — MCQ / multi-select / true-false per package
  attempts     — user's test run (answers, score, timing)
  purchases    — paid access records (idempotent via Stripe payment_id)
  leaderboard  — aggregated top scores per exam
"""
from datetime import datetime, timezone
from typing import Optional, Dict
from uuid import uuid4
from bson import ObjectId


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─── User ─────────────────────────────────────────────────────────────────────
def new_user(email: str, username: str, hashed_password: str, role: str = "user") -> dict:
    return {
        "email": email.lower().strip(),
        "username": username.strip(),
        "hashed_password": hashed_password,
        "role": role,                    # "user" | "admin"
        "is_active": True,
        "created_at": utcnow(),
        "updated_at": utcnow(),
        "profile": {
            "full_name": "",
            "avatar_url": "",
            "bio": "",
        },
        "stats": {
            "total_attempts": 0,
            "total_correct": 0,
            "exams_purchased": 0,
        },
    }


# ─── Exam ─────────────────────────────────────────────────────────────────────
def new_exam(
    title: str,
    slug: str,
    description: str,
    category: str,
    price_usd: float,
    thumbnail_url: str = "",
    tags: list = None,
) -> dict:
    return {
        "title": title,
        "slug": slug,                    # URL-friendly ID, e.g. "aws-saa-c03"
        "description": description,
        "category": category,            # e.g. "Cloud", "Agile", "Security"
        "price_usd": price_usd,
        "thumbnail_url": thumbnail_url,
        "tags": tags or [],
        "package_count": 6,             # always 6 packages per business rule
        "is_published": False,
        "total_questions": 0,           # denormalized counter (write-through)
        "avg_pass_rate": 0.0,
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }


def new_cert_metadata(
    name: str,
    collection_name: str,
    symbol: str,
    prompt_context: str,
    multi_choice_prompt_prefix: str,
    multi_choice_questions: int,
    multi_selection_prompt_prefix: str,
    category: str,
    short_brief: str,
    slug: str,
    duration: int = 0,
    disclaimer: str = "",
    what_learn: list = None,
    requirements: list = None,
) -> dict:
    return {
        "name": name,
        "collection_name": collection_name,
        "symbol": symbol,
        "prompt_context": prompt_context,
        "multi_choice_prompt_prefix": multi_choice_prompt_prefix,
        "multi_choice_questions": multi_choice_questions,
        "multi_selection_prompt_prefix": multi_selection_prompt_prefix,
        "category": category,
        "short_brief": short_brief,
        "slug": slug,
        "duration": duration,
        "disclaimer": disclaimer,
        "what_learn": what_learn or [],
        "requirements": requirements or [],
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }


# ─── Package ──────────────────────────────────────────────────────────────────
def new_package(
    exam_id: str,
    order: int,                          # 1–6
    title: str,
    description: str = "",
    time_limit_minutes: int = 60,
    pass_score_pct: int = 70,
) -> dict:
    return {
        "exam_id": exam_id,
        "order": order,
        "title": title,
        "description": description,
        "time_limit_minutes": time_limit_minutes,
        "pass_score_pct": pass_score_pct,
        "question_count": 0,            # denormalized, updated on question add
        "is_active": True,
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }


# ─── Question ─────────────────────────────────────────────────────────────────
def new_question(
    package_id: str,
    exam_id: str,
    text: str,
    q_type: str,                         # "single" | "multiple" | "true_false"
    options: list[dict],                 # [{"key": "A", "text": "...", "is_correct": bool}]
    explanation: str = "",
    tags: list = None,
    difficulty: str = "medium",          # "easy" | "medium" | "hard"
) -> dict:
    return {
        "package_id": package_id,
        "exam_id": exam_id,
        "text": text,
        "type": q_type,
        "options": options,              # embedded — avoids N+1 joins
        "explanation": explanation,
        "tags": tags or [],
        "difficulty": difficulty,
        "times_answered": 0,            # for analytics
        "times_correct": 0,
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }


def new_cert_question(
    question: str,
    options: Dict[str, str],
    answer: str,
    explanation: Dict[str, str],
    q_type: str = "multiple-choice",
    domain: int = 1,
    exported: int = 0,
    uuid: str | None = None,
) -> dict:
    return {
        "question": question,
        "options": options,
        "answer": answer,
        "explanation": explanation,
        "type": q_type,
        "domain": domain,
        "exported": exported,
        "uuid": uuid or str(uuid4()),
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }


# ─── Attempt ──────────────────────────────────────────────────────────────────
def new_attempt(user_id: str, package_id: str, exam_id: str) -> dict:
    return {
        "user_id": user_id,
        "package_id": package_id,
        "exam_id": exam_id,
        "status": "in_progress",        # "in_progress" | "completed" | "abandoned"
        "answers": [],                   # filled progressively
        "score": 0,
        "total_questions": 0,
        "correct_count": 0,
        "passed": False,
        "time_spent_seconds": 0,
        "started_at": utcnow(),
        "completed_at": None,
    }


def new_answer(question_id: str, selected_keys: list[str], is_correct: bool, time_seconds: int = 0) -> dict:
    return {
        "question_id": question_id,
        "selected_keys": selected_keys,
        "is_correct": is_correct,
        "time_seconds": time_seconds,
        "answered_at": utcnow(),
    }


# ─── Purchase ─────────────────────────────────────────────────────────────────
def new_purchase(
    user_id: str,
    exam_id: str,
    amount_usd: float,
    paypal_order_id: str,
    status: str = "completed",
) -> dict:
    return {
        "user_id": user_id,
        "exam_id": exam_id,
        "amount_usd": amount_usd,
        "paypal_order_id": paypal_order_id,
        "status": status,               # "pending" | "completed" | "refunded"
        "purchased_at": utcnow(),
        "expires_at": None,             # None = lifetime access
    }
