"""
app/api/v1/endpoints/users.py — User profile + admin user management
"""
from fastapi import APIRouter, Depends, HTTPException
from app.middleware.auth import get_current_user, get_current_admin
from app.services import user_service
from app.schemas.schemas import UpdateProfileRequest, OkResponse

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me/stats")
async def my_stats(current_user=Depends(get_current_user)):
    return await user_service.get_user_dashboard_stats(str(current_user["_id"]))


@router.patch("/me")
async def update_profile(data: UpdateProfileRequest, current_user=Depends(get_current_user)):
    result = await user_service.update_profile(
        str(current_user["_id"]),
        full_name=data.full_name,
        avatar_url=data.avatar_url,
    )
    if not result:
        raise HTTPException(404, "User not found")
    return result


@router.get("", dependencies=[Depends(get_current_admin)])
async def list_users(page: int = 1):
    return await user_service.list_users(page=page)


@router.patch("/{user_id}/active", dependencies=[Depends(get_current_admin)])
async def set_active(user_id: str, is_active: bool):
    ok = await user_service.set_user_active(user_id, is_active)
    if not ok:
        raise HTTPException(404, "User not found")
    return OkResponse(message=f"User {'activated' if is_active else 'deactivated'}")


"""
app/api/v1/endpoints/rag.py — RAG document management (admin)
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.middleware.auth import get_current_admin
from app.services import rag_service

rag_router = APIRouter(prefix="/rag", tags=["RAG"])


class IngestRequest(BaseModel):
    content: str
    source_name: str
    chunk_size: int = 500
    chunk_overlap: int = 50


@rag_router.post("/{exam_id}/ingest")
async def ingest_document(exam_id: str, data: IngestRequest, _=Depends(get_current_admin)):
    """Admin: ingest a document into the exam's vector store."""
    return await rag_service.ingest_document(
        exam_id=exam_id,
        content=data.content,
        source_name=data.source_name,
        chunk_size=data.chunk_size,
        chunk_overlap=data.chunk_overlap,
    )


@rag_router.get("/{exam_id}/documents")
async def list_documents(exam_id: str, _=Depends(get_current_admin)):
    return await rag_service.list_documents(exam_id)


@rag_router.delete("/{exam_id}/documents/{source_name}")
async def delete_document(exam_id: str, source_name: str, _=Depends(get_current_admin)):
    ok = await rag_service.delete_document(exam_id, source_name)
    if not ok:
        raise HTTPException(404, "Document not found")
    from app.schemas.schemas import OkResponse
    return OkResponse(message="Document deleted")
