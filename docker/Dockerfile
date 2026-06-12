FROM python:3.11-slim AS base

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# ── Dependencies stage ───────────────────────────────────────────────────────
FROM base AS deps
COPY requirements.txt .
RUN pip install -r requirements.txt

# ── Production stage ─────────────────────────────────────────────────────────
FROM base AS production

# Run as non-root
RUN addgroup --system app && adduser --system --ingroup app app

COPY --from=deps /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=deps /usr/local/bin /usr/local/bin

COPY --chown=app:app app/ ./app/
COPY --chown=app:app frontend/ ./frontend/

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
