# Architecture Overview

## Stack

- **Framework**: FastAPI (async)
- **Database**: MongoDB via Beanie ODM (async Motor driver)
- **Cache / Queue**: Redis + Celery
- **AI / RAG**: OpenAI API, LangChain, ChromaDB
- **Auth**: JWT (python-jose) + bcrypt passwords
- **Payments**: Stripe
- **Monitoring**: Prometheus, structlog

## Project Layout

```
app/
├── main.py               # App entry point, router registration
├── worker.py             # Celery worker
├── api/
│   └── v1/
│       └── endpoints/    # Route handlers (thin controllers)
│           ├── auth.py
│           ├── users.py
│           ├── exams.py
│           └── attempts.py
├── services/             # Business logic
│   ├── auth_service.py
│   ├── user_service.py
│   ├── exam_service.py
│   ├── attempt_service.py
│   ├── ai_service.py
│   ├── rag_service.py
│   └── payment_service.py
├── models/
│   └── documents.py      # Beanie ODM documents (MongoDB collections)
├── schemas/
│   └── schemas.py        # Pydantic request/response schemas
├── middleware/
│   └── auth.py           # JWT authentication middleware
├── core/
│   ├── config.py         # Settings (pydantic-settings)
│   ├── database.py       # MongoDB connection
│   ├── security.py       # Token helpers
│   └── cache.py          # Redis client
└── utils/
    └── dsa.py
scripts/
└── seed.py               # Database seeding
tests/
frontend/                 # Static JS frontend
```

## Request Flow

```
Client → Middleware (auth) → Endpoint (api/v1) → Service → Model (DB) / Cache / AI
```

## Key Domains

| Domain | Endpoint | Service |
|---|---|---|
| Auth | `/api/v1/auth` | `auth_service` |
| Users | `/api/v1/users` | `user_service` |
| Exams | `/api/v1/exams` | `exam_service` |
| Attempts | `/api/v1/attempts` | `attempt_service` |

## Notes

- All DB access goes through Beanie documents in `models/documents.py`.
- AI question generation is async; heavy jobs are offloaded to Celery.
- RAG pipeline uses ChromaDB as the vector store.
