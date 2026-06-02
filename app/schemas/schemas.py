"""
app/schemas/

Pydantic v2 schemas for request validation and response shaping.
Pydantic: Module 1 (FastAPI MVC) — validate input/output automatically.
"""
from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, EmailStr, Field, field_validator
import re


# ─── Shared ───────────────────────────────────────────────────────────────────

class PyObjectId(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        return str(v)


class OkResponse(BaseModel):
    ok: bool = True
    message: str = "success"


# ─── Auth ─────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field("", max_length=100)
    captcha_id: str
    captcha_answer: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    role: str


class RefreshRequest(BaseModel):
    refresh_token: str


# ─── User ─────────────────────────────────────────────────────────────────────

class UserProfile(BaseModel):
    full_name: str = ""
    avatar_url: str = ""
    bio: str = ""


class UserStats(BaseModel):
    total_attempts: int = 0
    total_correct: int = 0
    exams_purchased: int = 0


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    role: str
    is_active: bool
    profile: UserProfile
    stats: UserStats
    created_at: datetime


class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = Field(None, max_length=100)
    avatar_url: Optional[str] = None
    bio: Optional[str] = Field(None, max_length=500)


# ─── Exam ─────────────────────────────────────────────────────────────────────

class ExamCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    slug: str = Field(..., pattern=r"^[a-z0-9-]+$", max_length=100)
    description: str = Field(..., max_length=2000)
    category: str = Field(..., max_length=50)
    price_usd: float = Field(..., ge=0, le=9999)
    thumbnail_url: str = ""
    tags: List[str] = []


class ExamUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price_usd: Optional[float] = None
    thumbnail_url: Optional[str] = None
    tags: Optional[List[str]] = None
    is_published: Optional[bool] = None


class ExamSummary(BaseModel):
    id: str
    title: str
    slug: str
    description: str
    category: str
    price_usd: float
    thumbnail_url: str
    package_count: int
    total_questions: int
    avg_pass_rate: float
    is_published: bool
    tags: List[str]


class ExamDetail(ExamSummary):
    duration: int = 0
    disclaimer: str = ""
    learns: List[str] = []
    requirements: List[str] = []
    created_at: datetime
    updated_at: datetime


class CertMetadataCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=300)
    collection_name: str = Field(..., min_length=3, max_length=100)
    symbol: str = Field(..., min_length=2, max_length=50)
    prompt_context: str = Field(..., min_length=20, max_length=20000)
    multi_choice_prompt_prefix: str = Field(..., min_length=10, max_length=2000)
    multi_choice_questions: int = Field(..., ge=0, le=200)
    multi_selection_prompt_prefix: str = Field(..., min_length=10, max_length=2000)
    category: str = Field(..., min_length=2, max_length=100)
    short_brief: str = Field(..., min_length=10, max_length=2000)
    slug: str = Field(..., pattern=r"^[a-z0-9-]+$", max_length=100)
    duration: int = Field(0, ge=0, description="Duration in minutes")
    disclaimer: str = Field("", max_length=5000)
    what_learn: List[str] = []
    requirements: List[str] = []


class CertMetadataResponse(CertMetadataCreate):
    id: str
    created_at: datetime
    updated_at: datetime


class ExamListResponse(BaseModel):
    items: List[ExamSummary]
    total: int
    page: int
    page_size: int
    total_pages: int


# ─── Package ──────────────────────────────────────────────────────────────────

class PackageCreate(BaseModel):
    order: int = Field(..., ge=1, le=6)
    title: str = Field(..., min_length=3, max_length=200)
    description: str = ""
    time_limit_minutes: int = Field(60, ge=10, le=300)
    pass_score_pct: int = Field(70, ge=1, le=100)


class PackageResponse(BaseModel):
    id: str
    exam_id: str
    order: int
    title: str
    description: str
    time_limit_minutes: int
    pass_score_pct: int
    question_count: int
    is_active: bool


# ─── Question ─────────────────────────────────────────────────────────────────

class OptionSchema(BaseModel):
    key: str = Field(..., pattern=r"^[A-E]$")
    text: str = Field(..., min_length=1, max_length=1000)
    is_correct: bool


class QuestionCreate(BaseModel):
    text: str = Field(..., min_length=5, max_length=3000)
    type: str = Field(..., pattern=r"^(single|multiple|true_false)$")
    options: List[OptionSchema] = Field(..., min_length=2, max_length=5)
    explanation: str = Field("", max_length=2000)
    tags: List[str] = []
    difficulty: str = Field("medium", pattern=r"^(easy|medium|hard)$")

    @field_validator("options")
    @classmethod
    def at_least_one_correct(cls, v):
        if not any(o.is_correct for o in v):
            raise ValueError("At least one option must be correct")
        return v


class CertQuestionCreate(BaseModel):
    question: str = Field(..., min_length=10, max_length=3000)
    options: Dict[str, str] = Field(..., min_length=2)
    answer: str = Field(..., pattern=r"^[A-E]$")
    explanation: Dict[str, str] = Field(..., min_length=2)
    type: str = Field("multiple-choice", pattern=r"^(multiple-choice|single-choice|true-false)$")
    domain: int = Field(..., ge=1)
    exported: int = Field(0, ge=0)
    uuid: str = Field(..., min_length=1)


class CertQuestionResponse(CertQuestionCreate):
    id: str
    created_at: datetime
    updated_at: datetime


class QuestionPublic(BaseModel):
    """Question schema for test-takers — hides is_correct and explanation."""
    id: str
    text: str
    type: str
    options: List[dict]   # options without is_correct field
    tags: List[str]
    difficulty: str


class QuestionAdmin(BaseModel):
    """Full question with answers — admin/review only."""
    id: str
    package_id: str
    exam_id: str
    text: str
    type: str
    options: List[OptionSchema]
    explanation: str
    tags: List[str]
    difficulty: str
    times_answered: int
    times_correct: int


# ─── Attempt ──────────────────────────────────────────────────────────────────

class StartAttemptRequest(BaseModel):
    package_id: str


class SubmitAnswerRequest(BaseModel):
    question_id: str
    selected_keys: List[str] = Field(..., min_length=1)
    time_seconds: int = Field(0, ge=0)


class SubmitAttemptRequest(BaseModel):
    attempt_id: str


class AnswerResult(BaseModel):
    question_id: str
    selected_keys: List[str]
    correct_keys: List[str]
    is_correct: bool
    explanation: str


class AttemptResult(BaseModel):
    attempt_id: str
    score: float
    correct_count: int
    total_questions: int
    passed: bool
    time_spent_seconds: int
    answers: List[AnswerResult]
    pass_score_pct: int


class AttemptSummary(BaseModel):
    id: str
    package_id: str
    exam_id: str
    status: str
    score: float
    passed: bool
    started_at: datetime
    completed_at: Optional[datetime]


# ─── Payment ──────────────────────────────────────────────────────────────────

class CreateCheckoutRequest(BaseModel):
    exam_id: str


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class PurchaseResponse(BaseModel):
    id: str
    exam_id: str
    amount_usd: float
    status: str
    purchased_at: datetime


# ─── AI ───────────────────────────────────────────────────────────────────────

class AskHintRequest(BaseModel):
    question_id: str
    user_question: str = Field(..., max_length=500)


class StudyRequest(BaseModel):
    question: str = Field(..., max_length=1000)
    exam_context: Optional[str] = None


class AIResponse(BaseModel):
    answer: str
    sources: List[str] = []
    model_used: str


# ─── Leaderboard ──────────────────────────────────────────────────────────────

class LeaderboardEntry(BaseModel):
    rank: int
    username: str
    score: float
    passed: bool
    completed_at: datetime


class LeaderboardResponse(BaseModel):
    exam_id: str
    entries: List[LeaderboardEntry]
