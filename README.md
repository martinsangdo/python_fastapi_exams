# ExamPrep Platform

A full-stack exam preparation platform built with **FastAPI + MongoDB**, demonstrating every technique from the Software Engineer & Architect with AI curriculum.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (MVC), Python 3.11 |
| Database | MongoDB (Motor async driver) |
| Auth | JWT (access + refresh tokens) |
| Cache | Redis (cache-aside, TTL) |
| Queue | Celery + Redis broker |
| Container | Docker + Docker Compose |
| CI/CD | GitHub Actions |
| Monitoring | Prometheus + Grafana |
| Security | OWASP hardening, prompt injection guard |
| AI | OpenAI / Gemini API — question hints, auto-grading |
| RAG | ChromaDB + LangChain — AI study assistant |

---

## Curriculum Coverage Map

### Module 1 — DSA & System Design
- `app/utils/dsa.py` — Hash maps for O(1) question lookup, heap for leaderboard, tree for topic taxonomy
- `app/services/exam_service.py` — 5-Step system design: clarify → estimate → design → deep-dive → trade-offs

### Module 2 — Solutions Architect
- `app/core/cache.py` — Redis cache-aside strategy with TTL & invalidation
- `app/core/config.py` — CAP theorem choices documented (MongoDB = CP)
- `app/services/payment_service.py` — Idempotency keys, retry with exponential backoff

### Module 3 — DevOps
- `docker/docker-compose.yml` — Multi-service orchestration
- `.github/workflows/ci.yml` — GitHub Actions: test → build → deploy
- `scripts/seed.py` — Automated DB seeding

### Module 4 — Cloud AWS (annotated)
- `docs/aws_architecture.md` — VPC, ECS, RDS, Lambda design
- `app/core/config.py` — Env-based config for cloud deployment

### Module 5 — Agentic AI
- `app/services/ai_service.py` — LLM integration, streaming, function calling
- `app/services/rag_service.py` — RAG pipeline: chunk → embed → store → retrieve
- `app/api/v1/endpoints/ai.py` — Agentic study assistant endpoint

---

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env          # fill in your keys

# 2. Run everything
docker compose up --build

# 3. Seed sample data
docker compose exec api python scripts/seed.py

# 4. Visit
# API docs:  http://localhost:8000/docs
# Grafana:   http://localhost:3000  (admin/admin)
```

---

## Project Structure

```
examprep/
├── app/
│   ├── api/v1/endpoints/   # Route handlers (MVC: Controller)
│   │   ├── auth.py
│   │   ├── exams.py
│   │   ├── packages.py
│   │   ├── questions.py
│   │   ├── attempts.py
│   │   ├── payments.py
│   │   ├── users.py
│   │   └── ai.py
│   ├── core/               # Config, DB, Cache, Security
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── cache.py
│   │   └── security.py
│   ├── models/             # MongoDB document models (MVC: Model)
│   ├── schemas/            # Pydantic request/response schemas
│   ├── services/           # Business logic (MVC: Service layer)
│   ├── middleware/         # Auth, CORS, Rate-limit, Logging
│   └── utils/              # DSA helpers, validators, AI guard
├── tests/                  # pytest unit + integration tests
├── scripts/                # seed.py, migrate.py
├── docker/
│   └── docker-compose.yml
├── .github/workflows/ci.yml
├── .env.example
└── requirements.txt
```
