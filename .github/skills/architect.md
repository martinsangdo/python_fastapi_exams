---
name: Architect
version: 0.1
read_first: true
description: |
  Minimal project-level architect guidance for this repository. Keep concise —
  features and responsibilities are still evolving. Intended to be read first
  by tooling and maintainers to provide high-level constraints and token-saving
  hints.
tags: [architect, project, guidance]
---


# Architect Skill (Concise)

Purpose: a short, evolving guide for tools and maintainers to read first.

Scope: high-level module responsibilities, primary workflows, and integration
points. Keep deliberately brief — avoid implementation details.

Project goals:
- Provide a lightweight exam/quiz backend with AI-assisted features and
  simple frontend; keep services modular and testable.

Key modules (one-line each):
- `app/main.py`: HTTP entrypoint, FastAPI app and routes registration.
- `app/worker.py`: background job worker (async tasks, long-running jobs).
- `app/api/v1/endpoints/*`: request handlers (`attempts.py`, `auth.py`,
  `exams.py`, `users.py`) — validate input, call services, return responses.
- `app/core/cache.py`: cache wrapper (Redis) used by services for performance.
- `app/core/config.py`: configuration variables and environment mappings.
- `app/core/database.py`: DB session/ORM setup and helpers.
- `app/core/security.py`: auth helpers, password hashing and token utilities.
- `app/middleware/auth.py`: request auth enforcement and user injection.
- `app/models/*`: ORM/document schemas for persistence (`documents.py`).
- `app/schemas/schemas.py`: Pydantic schemas for request/response contracts.
- `app/services/*`: business logic layer (AI, attempts, auth, exams, payment,
  rag, users). Services are stateless and orchestrate core + external calls.
- `app/utils/dsa.py`: helper algorithms and utilities used by services.
- `frontend/`: static UI pages and client-side JS that call the API.
- `docker/`: container and orchestration config for local/dev runs.

Primary workflow (concise):
Client -> `frontend` or external client -> HTTP -> `app/main` -> middleware
-> endpoint handler -> service layer -> `core` (db/cache) and `models` ->
response. Background jobs use `app/worker.py` -> services -> persistence.

Integration points:
- AI/RAG (`services/ai_service.py`, `services/rag_service.py`) call external
  LLM or embedding endpoints; keep calls behind service interfaces.
- Payment (`services/payment_service.py`) integrates with external gateway.
- Worker tasks handle long-running processing, retries and async flows.

Non-goals / constraints:
- Not a detailed design doc — keep expansions in `docs/` and code comments.
- Avoid embedding large code or data in this file to preserve token budget.
- Mark any sensitive integration details as environment-config only.

Where to look for details:
- HTTP handlers: `app/api/v1/endpoints/`
- Business logic: `app/services/`
- Persistence/setup: `app/core/database.py`, `app/models/`

Contact / maintainers: add a short pointer here when available.

Notes:
- Update this file when major architectural shifts occur; keep concise.

