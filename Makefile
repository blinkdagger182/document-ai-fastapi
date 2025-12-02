.PHONY: help install dev test migrate run worker docker-up docker-down deploy-gcp

help:
	@echo "DocumentAI Backend - Available commands:"
	@echo "  make install      - Install dependencies"
	@echo "  make dev          - Run development server"
	@echo "  make worker       - Run Celery worker"
	@echo "  make test         - Run tests"
	@echo "  make migrate      - Run database migrations"
	@echo "  make docker-up    - Start Docker Compose services"
	@echo "  make docker-down  - Stop Docker Compose services"
	@echo "  make deploy-gcp   - Deploy to GCP Cloud Run"

install:
	pip install -r requirements.txt

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

worker:
	celery -A app.workers.celery_app worker -Q ocr,compose --loglevel=info

test:
	pytest tests/ -v

migrate:
	alembic upgrade head

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

deploy-gcp:
	bash deployment/gcp-deploy.sh
