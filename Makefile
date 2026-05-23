# ExamPrep — Developer shortcuts
.PHONY: help dev test seed lint docker-up docker-down

help:
	@echo ""
	@echo "  ExamPrep — Available commands"
	@echo "  ─────────────────────────────────────────────"
	@echo "  make dev        Start API in dev mode (hot reload)"
	@echo "  make test       Run all pytest tests"
	@echo "  make seed       Seed MongoDB with sample data"
	@echo "  make lint       Lint with ruff"
	@echo "  make docker-up  Start full stack (Docker Compose)"
	@echo "  make docker-down Stop all containers"
	@echo ""

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v --tb=short

seed:
	python scripts/seed.py

lint:
	ruff check app/ tests/

docker-up:
	docker compose -f docker/docker-compose.yml up --build -d

docker-down:
	docker compose -f docker/docker-compose.yml down

worker:
	celery -A app.worker worker --loglevel=info --concurrency=4

install:
	pip install -r requirements.txt
