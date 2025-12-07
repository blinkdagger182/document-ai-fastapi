# DocumentAI Backend - Deployment Guide

## Prerequisites

- GCP account with billing enabled
- `gcloud` CLI installed and configured
- Supabase project (database + storage)

## Quick Deploy to GCP

### Step 1: Configure Environment

```bash
export GCP_PROJECT_ID="your-project-id"
export GCP_REGION="us-central1"
export DATABASE_URL="postgresql://postgres:PASSWORD@db.xxx.supabase.co:5432/postgres"
export SUPABASE_URL="https://xxx.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="your-service-role-key"
export SUPABASE_BUCKET_NAME="documentai-storage"
```

### Step 2: Enable GCP APIs

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  cloudtasks.googleapis.com \
  --project=$GCP_PROJECT_ID
```

### Step 3: Create Supabase Storage Bucket

1. Go to: https://supabase.com/dashboard/project/YOUR_PROJECT/storage/buckets
2. Create bucket: `documentai-storage` (Private)

### Step 4: Deploy All Services

```bash
chmod +x deployment/gcp/deploy-all.sh
./deployment/gcp/deploy-all.sh
```

This deploys:
- API Service (public)
- OCR Worker (private)
- Composer Worker (private)
- Cloud Task queues

### Step 5: Test

```bash
API_URL=$(gcloud run services describe documentai-api \
  --region $GCP_REGION --format 'value(status.url)')

curl $API_URL/api/v1/health
# Expected: {"status":"ok"}
```

---

## Local Development

### Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Supabase credentials

# Run migrations
alembic upgrade head
python scripts/init_db.py

# Start API
uvicorn app.main:app --reload --port 8080
```

### Test Locally

```bash
curl http://localhost:8080/api/v1/health
open http://localhost:8080/docs
```

---

## Monitoring

### View Logs

```bash
# API logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=documentai-api" --limit 20

# Worker logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=documentai-ocr-worker" --limit 20
```

### Check Services

```bash
gcloud run services list --region=$GCP_REGION
gcloud tasks queues list --location=$GCP_REGION
```

---

## Troubleshooting

### Database Connection Issues
- Verify DATABASE_URL is correct
- Check Supabase project is active

### Storage Upload Failures
- Verify bucket exists and is private
- Check SUPABASE_SERVICE_ROLE_KEY is correct

### Workers Not Processing
- Check Cloud Task queues exist
- Verify IAM permissions for Cloud Tasks to invoke workers

---

## SwiftUI Integration

Update your iOS app with the deployed API URL:

```swift
let API_BASE_URL = "https://documentai-api-xxx.run.app/api/v1"
```
