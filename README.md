# DocumentAI Backend - CommonForms Only

Minimal FastAPI backend for CommonForms document processing.

## Features

- **Document Upload**: PDF upload with Supabase Storage
- **CommonForms Processing**: Auto-detect and create fillable form fields
- **Field Management**: Store and retrieve detected fields
- **PDF Composition**: Generate filled PDFs

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Supabase credentials

# Start API
uvicorn app.main:app --reload --port 8080
```

## API Endpoints

- `POST /api/v1/documents/init-upload` - Upload PDF
- `POST /api/v1/process/commonforms/{document_id}` - Process with CommonForms
- `GET /api/v1/process/status/{job_id}` - Check processing status
- `GET /api/v1/documents/{document_id}` - Get document details
- `POST /api/v1/documents/{document_id}/values` - Submit field values
- `GET /api/v1/documents/{document_id}/download` - Download filled PDF

## Deployment

```bash
# Deploy CommonForms worker
gcloud builds submit --config cloudbuild-worker.yaml

# Deploy main API
gcloud run deploy documentai-api --source .
```
