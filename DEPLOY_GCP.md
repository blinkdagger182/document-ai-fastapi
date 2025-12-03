# Deploy to GCP - Complete Guide

## Architecture Overview

```
SwiftUI App
    ↓ HTTPS
Cloud Run (API) ← You call this
    ↓ Cloud Tasks
Cloud Run (OCR Worker) ← Processes documents
Cloud Run (Composer Worker) ← Generates PDFs
    ↓
Supabase (Database + Storage)
```

## Prerequisites

1. **GCP Account** with billing enabled
2. **GCP Project** created
3. **gcloud CLI** installed and authenticated
4. **Supabase** database (already set up ✅)

## Step 1: Set Up GCP Project

```bash
# Set your project ID
export GCP_PROJECT_ID="your-project-id"
export GCP_REGION="us-central1"

# Set project
gcloud config set project $GCP_PROJECT_ID

# Enable required APIs
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  cloudtasks.googleapis.com \
  --project=$GCP_PROJECT_ID
```

## Step 2: Get Supabase Service Role Key

1. Go to: https://supabase.com/dashboard/project/iixekrmukkpdmmqoheed/settings/api
2. Copy the **service_role** key (not anon key!)
3. Save it for deployment

## Step 3: Configure Environment

```bash
# Edit deployment/gcp/.env.production
cd deployment/gcp
cp .env.production .env.production.local

# Update these values:
# - GCP_PROJECT_ID
# - SUPABASE_SERVICE_ROLE_KEY
```

## Step 4: Deploy Everything

```bash
# Load environment variables
source deployment/gcp/.env.production.local

# Make script executable
chmod +x deployment/gcp/deploy-all.sh

# Deploy all services
./deployment/gcp/deploy-all.sh
```

This will:
1. ✅ Create Cloud Task queues (ocr-queue, compose-queue)
2. ✅ Build and deploy OCR Worker to Cloud Run
3. ✅ Build and deploy Composer Worker to Cloud Run
4. ✅ Build and deploy API to Cloud Run
5. ✅ Configure IAM permissions

## Step 5: Test Deployment

```bash
# Get API URL
API_URL=$(gcloud run services describe documentai-api \
  --region $GCP_REGION \
  --format 'value(status.url)' \
  --project=$GCP_PROJECT_ID)

# Test health endpoint
curl $API_URL/api/v1/health

# Should return: {"status":"ok"}
```

## Step 6: Test Full Workflow

```bash
# 1. Upload a document
curl -X POST $API_URL/api/v1/documents/init-upload \
  -F "file=@test.pdf"

# Save the documentId from response

# 2. Process document
curl -X POST $API_URL/api/v1/documents/{documentId}/process

# 3. Check status (poll until ready)
curl $API_URL/api/v1/documents/{documentId}

# 4. Submit values
curl -X POST $API_URL/api/v1/documents/{documentId}/values \
  -H "Content-Type: application/json" \
  -d '{"values": [{"fieldRegionId": "uuid", "value": "test", "source": "manual"}]}'

# 5. Compose PDF
curl -X POST $API_URL/api/v1/documents/{documentId}/compose

# 6. Download filled PDF
curl $API_URL/api/v1/documents/{documentId}/download
```

## Cost Estimate (Free Tier)

### What's FREE:
- ✅ Cloud Run API: 2M requests/month
- ✅ Cloud Run Workers: 360K GB-seconds/month
- ✅ Cloud Tasks: 1M tasks/month
- ✅ Supabase: 500MB DB, 1GB storage
- ✅ Cloud Build: 120 build-minutes/day

### Solo User (10-50 docs/month):
**Total: RM0-5/month** (within free tiers!)

### Light Usage (100-500 docs/month):
- Cloud Run: RM5-15
- Cloud Tasks: RM0 (free)
- Supabase: RM0 (free tier)
- **Total: RM5-15/month**

## Architecture Benefits

### ✅ Scales to Zero
- API only runs when receiving requests
- Workers only run when processing
- No idle costs!

### ✅ No Redis Needed
- Cloud Tasks handles queuing
- No RM48/month Redis cost
- Simpler architecture

### ✅ Separate Workers
- OCR worker can scale independently
- Composer worker can scale independently
- Better resource utilization

## Monitoring

### View Logs
```bash
# API logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=documentai-api" --limit 50

# OCR worker logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=documentai-ocr-worker" --limit 50

# Composer worker logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=documentai-composer-worker" --limit 50
```

### View Cloud Tasks
```bash
# List tasks in OCR queue
gcloud tasks list --queue=ocr-queue --location=$GCP_REGION

# List tasks in compose queue
gcloud tasks list --queue=compose-queue --location=$GCP_REGION
```

## Troubleshooting

### Workers not being invoked
```bash
# Check IAM permissions
gcloud run services get-iam-policy documentai-ocr-worker --region=$GCP_REGION

# Should show Cloud Tasks service account with run.invoker role
```

### Database connection issues
```bash
# Test from Cloud Run
gcloud run services update documentai-api \
  --set-env-vars "DATABASE_URL=$DATABASE_URL" \
  --region=$GCP_REGION
```

### Storage issues
```bash
# Verify Supabase bucket exists
# Go to: https://supabase.com/dashboard/project/iixekrmukkpdmmqoheed/storage/buckets

# Create bucket if needed: documentai-storage
```

## Update Deployment

```bash
# Redeploy API only
gcloud builds submit --tag gcr.io/$GCP_PROJECT_ID/documentai-api
gcloud run deploy documentai-api \
  --image gcr.io/$GCP_PROJECT_ID/documentai-api \
  --region=$GCP_REGION

# Redeploy OCR worker only
gcloud builds submit --tag gcr.io/$GCP_PROJECT_ID/documentai-ocr-worker \
  --file=workers/ocr/Dockerfile
gcloud run deploy documentai-ocr-worker \
  --image gcr.io/$GCP_PROJECT_ID/documentai-ocr-worker \
  --region=$GCP_REGION

# Redeploy Composer worker only
gcloud builds submit --tag gcr.io/$GCP_PROJECT_ID/documentai-composer-worker \
  --file=workers/composer/Dockerfile
gcloud run deploy documentai-composer-worker \
  --image gcr.io/$GCP_PROJECT_ID/documentai-composer-worker \
  --region=$GCP_REGION
```

## SwiftUI Integration

Once deployed, update your SwiftUI app:

```swift
let API_BASE_URL = "https://documentai-api-xxx-uc.a.run.app/api/v1"
```

Replace with your actual Cloud Run URL.

## Next Steps

1. ✅ Deploy to GCP
2. ✅ Test all endpoints
3. ✅ Integrate with SwiftUI app
4. ✅ Monitor usage and costs
5. ✅ Scale as needed

---

**Your backend is now production-ready on GCP!** 🚀
