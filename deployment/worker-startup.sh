#!/bin/bash
# Startup script for GCP VM running Celery workers

set -e

# Update system
apt-get update
apt-get install -y python3-pip git libpq-dev gcc g++ libgomp1

# Clone repository (or use deployment artifact)
cd /opt
git clone https://github.com/your-org/documentai-backend.git
cd documentai-backend

# Install dependencies
pip3 install -r requirements.txt

# Set environment variables (from GCP Secret Manager)
export DATABASE_URL=$(gcloud secrets versions access latest --secret="documentai-db-url")
export REDIS_URL=$(gcloud secrets versions access latest --secret="documentai-redis-url")
export CELERY_BROKER_URL=$REDIS_URL
export CELERY_RESULT_BACKEND=$REDIS_URL
export STORAGE_BACKEND=gcs
export OCR_BACKEND=local
export GCS_BUCKET_NAME=$(gcloud secrets versions access latest --secret="documentai-bucket")

# Start Celery worker
celery -A app.workers.celery_app worker \
  -Q ocr,compose \
  --loglevel=info \
  --concurrency=4 \
  --max-tasks-per-child=10
