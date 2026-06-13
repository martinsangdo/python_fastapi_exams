"""
app/api/v1/endpoints/attempts.py — Test attempt routes
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from app.schemas.schemas import StartAttemptRequest, SubmitAnswerRequest, SubmitAttemptRequest
from app.services import attempt_service
from app.middleware.auth import get_current_user

router = APIRouter(prefix="/attempts", tags=["Attempts"])


@router.post("", status_code=201)
async def start_attempt(data: StartAttemptRequest, current_user=Depends(get_current_user)):
    print(f"[DEBUG] start_attempt: package_id={data.package_id!r} exam_id={data.exam_id!r}")
    try:
        return await attempt_service.start_attempt(str(current_user["_id"]), data.package_id, data.exam_id)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{attempt_id}/answers")
async def submit_answer(
    attempt_id: str,
    data: SubmitAnswerRequest,
    current_user=Depends(get_current_user),
):
    try:
        return await attempt_service.submit_answer(
            attempt_id=attempt_id,
            user_id=str(current_user["_id"]),
            question_id=data.question_id,
            selected_keys=data.selected_keys,
            time_seconds=data.time_seconds,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{attempt_id}/finish")
async def finish_attempt(
    attempt_id: str,
    correct_count: int = None,
    total_questions: int = None,
    current_user=Depends(get_current_user),
):
    try:
        return await attempt_service.finish_attempt(attempt_id, str(current_user["_id"]), correct_count, total_questions)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("")
async def list_my_attempts(
    current_user=Depends(get_current_user),
    page: int = Query(1, ge=1),
):
    return await attempt_service.get_user_attempts(str(current_user["_id"]), page=page)


"""
app/api/v1/endpoints/payments.py — Payment routes (PayPal)
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from app.schemas.schemas import CreateCheckoutRequest
from app.services import payment_service
from app.middleware.auth import get_current_user

payments_router = APIRouter(prefix="/payments", tags=["Payments"])


@payments_router.post("/checkout")
async def create_checkout(data: CreateCheckoutRequest, current_user=Depends(get_current_user)):
    """Create a PayPal order. Returns approval_url — redirect the user there to pay."""
    try:
        return await payment_service.create_checkout_session(
            str(current_user["_id"]), data.exam_id
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@payments_router.post("/capture")
async def capture_payment(order_id: str, current_user=Depends(get_current_user)):
    """
    Capture an approved PayPal order and grant access to the exam.
    Call this after the user returns from the PayPal approval page
    (the return_url receives ?token=ORDER_ID — pass that here as order_id).
    """
    try:
        return await payment_service.capture_order(str(current_user["_id"]), order_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@payments_router.post("/webhook")
async def paypal_webhook(request: Request):
    """PayPal webhook — PAYMENT.CAPTURE.COMPLETED as a fulfill fallback."""
    payload = await request.body()
    headers = dict(request.headers)
    try:
        return await payment_service.handle_webhook(payload, headers)
    except ValueError as e:
        raise HTTPException(400, str(e))


@payments_router.get("/my-purchases")
async def my_purchases(current_user=Depends(get_current_user)):
    return await payment_service.list_user_purchases(str(current_user["_id"]))


"""
app/api/v1/endpoints/ai.py — AI / Agentic features routes
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from app.schemas.schemas import AskHintRequest, StudyRequest
from app.services import ai_service
from app.middleware.auth import get_current_user

ai_router = APIRouter(prefix="/ai", tags=["AI"])


@ai_router.post("/hint")
async def get_hint(data: AskHintRequest, current_user=Depends(get_current_user)):
    hint = await ai_service.get_question_hint(
        data.question_id, data.user_question, str(current_user["_id"])
    )
    return {"hint": hint}


@ai_router.get("/explain/{question_id}")
async def explain_answer(question_id: str, current_user=Depends(get_current_user)):
    return await ai_service.get_answer_explanation(question_id)


@ai_router.post("/study/stream")
async def study_stream(data: StudyRequest, current_user=Depends(get_current_user)):
    """
    Streaming study assistant — Module 5.
    Returns server-sent events (SSE) with token-by-token AI response.
    """
    async def generate():
        async for token in ai_service.study_assistant_stream(
            question=data.question,
            conversation_history=[],
            exam_id=data.exam_context,
        ):
            yield f"data: {token}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@ai_router.post("/agent")
async def agentic_study(data: StudyRequest, current_user=Depends(get_current_user)):
    """Agentic loop — Module 5: Agent Loop."""
    if not data.exam_context:
        raise HTTPException(400, "exam_context (exam_id) required for agent session")
    return await ai_service.agentic_study_session(
        task=data.question,
        exam_id=data.exam_context,
        user_id=str(current_user["_id"]),
    )
