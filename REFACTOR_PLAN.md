# Refactoring Plan: Celery → Cloud Tasks + Cloud Run

## Changes Required:

### 1. Remove Celery Dependencies
- Remove Celery and Redis from requirements
- Remove `app/workers/celery_app.py`
- Remove Celery task decorators

### 2. Create Cloud Tasks Service
- `app/services/cloud_tasks.py` - Enqueue OCR and compose jobs
- Configure Cloud Tasks client
- Create task queues

### 3. Convert Workers to HTTP Services

#### OCR Worker (separate Cloud Run service)
- New folder: `workers/ocr/`
- `workers/ocr/main.py` - FastAPI app with POST /ocr endpoint
- `workers/ocr/Dockerfile` - Container with PaddleOCR
- Receives `document_id` via HTTP POST
- Returns status

#### PDF Composer Worker (separate Cloud Run service)
- New folder: `workers/composer/`
- `workers/composer/main.py` - FastAPI app with POST /compose endpoint
- `workers/composer/Dockerfile` - Container with PyMuPDF
- Receives `document_id` via HTTP POST
- Returns status

### 4. Update API Backend
- Replace Celery task calls with Cloud Tasks enqueue
- Update `app/routers/documents.py`
- Add Cloud Tasks configuration

### 5. Deployment Structure
```
├── api/                    # Main FastAPI API (Cloud Run)
├── workers/
│   ├── ocr/               # OCR worker (Cloud Run)
│   └── composer/          # PDF composer (Cloud Run)
└── deployment/
    └── gcp/               # Deployment scripts
```

### 6. GCP Resources Needed
- 3 Cloud Run services (api, ocr-worker, composer-worker)
- 2 Cloud Task queues (ocr-queue, compose-queue)
- Service account with proper permissions
- Supabase connection (already working)

## Deployment Steps:
1. Build and deploy API to Cloud Run
2. Build and deploy OCR worker to Cloud Run
3. Build and deploy Composer worker to Cloud Run
4. Create Cloud Task queues
5. Configure IAM permissions
6. Test end-to-end flow

Starting refactor now...
