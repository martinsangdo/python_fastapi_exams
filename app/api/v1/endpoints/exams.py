"""
app/api/v1/endpoints/exams.py — Exam + Package + Question routes
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from app.schemas.schemas import (
    ExamCreate, ExamUpdate, ExamListResponse,
    PackageCreate, PackageResponse,
    QuestionCreate,
)
from app.services import exam_service
from app.middleware.auth import get_current_user, get_current_admin, get_optional_user

router = APIRouter(prefix="/exams", tags=["Exams"])


# ── Public: browse exams ─────────────────────────────────────────────────────

@router.get("", response_model=ExamListResponse)
async def list_exams(
    category: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
):
    return await exam_service.list_exams(category=category, page=page, page_size=page_size)


@router.get("/categories")
async def list_categories():
    return {"categories": await exam_service.list_cert_categories()}


@router.get("/autocomplete")
async def autocomplete(q: str = Query(..., min_length=1)):
    return {"results": await exam_service.autocomplete_exams(q)}


@router.get("/{slug}")
async def get_exam(slug: str, user=Depends(get_optional_user)):
    exam = await exam_service.get_exam_by_slug(slug)
    if not exam:
        raise HTTPException(404, "Exam not found")
    return exam


@router.get("/{exam_id}/analytics")
async def exam_analytics(exam_id: str, _=Depends(get_current_admin)):
    return await exam_service.get_exam_analytics(exam_id)


@router.get("/{exam_id}/leaderboard")
async def leaderboard(exam_id: str, top_n: int = Query(10, ge=3, le=50)):
    return {"exam_id": exam_id, "entries": await exam_service.get_leaderboard(exam_id, top_n)}


# ── Admin: manage exams ───────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_exam(data: ExamCreate, _=Depends(get_current_admin)):
    try:
        return await exam_service.create_exam(data)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.patch("/{exam_id}")
async def update_exam(exam_id: str, data: ExamUpdate, _=Depends(get_current_admin)):
    result = await exam_service.update_exam(exam_id, data)
    if not result:
        raise HTTPException(404, "Exam not found")
    return result


# ── Packages ─────────────────────────────────────────────────────────────────

@router.get("/{exam_id}/packages")
async def list_packages(exam_id: str, current_user=Depends(get_current_user)):
    from app.services.payment_service import has_access
    from bson import ObjectId
    user_id = str(current_user["_id"])
    packages = await exam_service.list_packages(exam_id)

    # Mark which packages the user has access to
    has = await has_access(user_id, exam_id)
    for p in packages:
        p["has_access"] = has
    return packages


@router.post("/{exam_id}/packages", status_code=201)
async def create_package(exam_id: str, data: PackageCreate, _=Depends(get_current_admin)):
    try:
        return await exam_service.create_package(exam_id, data)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── Questions ─────────────────────────────────────────────────────────────────

@router.get("/{exam_id}/packages/{package_id}/questions")
async def list_questions(exam_id: str, package_id: str, current_user=Depends(get_current_user)):
    from app.services.payment_service import has_access
    user_id = str(current_user["_id"])
    if not await has_access(user_id, exam_id):
        raise HTTPException(403, "Purchase this exam to access questions")
    return await exam_service.list_questions_public(package_id)


@router.post("/{exam_id}/packages/{package_id}/questions", status_code=201)
async def add_question(exam_id: str, package_id: str, data: QuestionCreate, _=Depends(get_current_admin)):
    try:
        return await exam_service.add_question(package_id, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
