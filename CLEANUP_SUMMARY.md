# DocumentAI FastAPI Cleanup Summary

## What Was Removed

### GCP Cloud Run Services (Deleted)
- ✅ `documentai-ocr-worker` - OCR detection worker
- ✅ `documentai-vision-worker` - Vision AI worker  
- ✅ `documentai-cf-worker` - Old CommonForms worker (duplicate)

### Code/Directories Removed
- `workers/ocr/` - OCR worker code
- `workers/vision/` - Vision AI worker code
- `workers/composer/` - PDF composer worker
- `workers/cf/` - Old CF worker directory
- `app/routers/hybrid.py` - Hybrid detection router
- All hybrid detection modules (geometric, ensemble, etc.)
- `tests/` - Test files
- `docs/` - Documentation files
- `deployment/terraform/` - Terraform configs
- Test files and PDFs in root

## What Remains (Active)

### GCP Cloud Run Services
- ✅ `documentai-api` - Main FastAPI application
- ✅ `documentai-commonforms-worker` - CommonForms processing worker

### Core Code Structure
```
app/
├── routers/
│   ├── commonforms.py    # CommonForms endpoints
│   ├── documents.py      # Document CRUD
│   └── health.py         # Health checks
├── services/
│   ├── storage.py        # Storage abstraction
│   └── supabase_storage.py
├── models/               # Database models
└── schemas/              # Pydantic schemas

workers/
└── cf_worker.py          # CommonForms worker service
```

## API Endpoints (Active)

### Document Management
- `POST /api/v1/documents/init-upload` - Upload PDF
- `GET /api/v1/documents/{id}` - Get document details
- `POST /api/v1/documents/{id}/values` - Submit field values
- `GET /api/v1/documents/{id}/download` - Download filled PDF

### CommonForms Processing
- `POST /api/v1/process/commonforms/{document_id}` - Start processing
- `GET /api/v1/process/status/{job_id}` - Check job status
- `POST /api/v1/process/commonforms/{document_id}/sync` - Sync processing (dev)
- `POST /api/v1/process/commonforms/{document_id}/mock` - Mock response (testing)

### Health
- `GET /api/v1/health` - API health check
- `GET /health` - Worker health check

## Testing

Service health checks passed:
```bash
curl https://documentai-api-824241800977.us-central1.run.app/api/v1/health
# {"status":"ok"}

curl https://documentai-commonforms-worker-824241800977.us-central1.run.app/health
# {"status":"ok","service":"commonforms-worker"}
```

## Known Issues

- Supabase storage occasionally returns 504 Gateway Timeout
- This is a Supabase infrastructure issue, not application code
- Retry logic may be needed for production use

## Dependencies Cleaned

Removed from `requirements.txt`:
- `alembic` (database migrations - not needed for single-user)
- `google-cloud-tasks` (async workers)
- `boto3` (AWS S3)
- `python-jose`, `passlib` (auth - not needed)
- `openai`, `google-generativeai` (Vision AI)
- `opencv-python`, `scipy` (geometric detection)
- `pytest`, `hypothesis` (testing)

Kept only:
- FastAPI core
- SQLAlchemy + PostgreSQL
- Supabase Storage
- PyMuPDF (PDF processing)
- CommonForms + PyTorch CPU
