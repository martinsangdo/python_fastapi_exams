"""
app/core/config.py

Architecture decisions documented here (ADR style):
- MongoDB chosen for CP (Consistency + Partition tolerance) per CAP theorem
- Redis for caching: reduces DB load by ~90% on hot exam data (Module 2)
- JWT stateless auth: scales horizontally without shared session store
- DRY principle: all settings in one place, consumed via dependency injection
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "ExamPrep"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    FRONTEND_URL: str = "http://localhost:3000"

    # Security
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"

    # MongoDB (CP system — consistent reads, partition tolerant)
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "examprep"

    # Redis cache
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_DEFAULT_TTL: int = 300  # seconds

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Payment
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # AI
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    AI_MODEL: str = "gpt-4o-mini"
    AI_MAX_TOKENS: int = 1000

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # Monitoring
    PROMETHEUS_ENABLED: bool = True


@lru_cache()  # AHA principle: compute once, reuse everywhere
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
