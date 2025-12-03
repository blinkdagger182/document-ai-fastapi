#!/bin/bash
# Deploy all services to GCP Cloud Run

set -e

# Configuration
PROJECT_ID=${GCP_PROJECT_ID:-"your-project-id"}
REGION=${GCP_REGION:-"us-central1"}

echo "🚀 Deploying DocumentAI to GCP"
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# 1. Create Cloud Task queues
echo "📋 Creating Cloud Task queues..."
gcloud tasks queues create ocr-queue \
  --location=$REGION \
  --max-dispatches-per-second=10 \
  --max-concurrent-dispatches=100 \
  --project=$PROJECT_ID \
  || echo "OCR queue already exists"

gcloud tasks queues create compose-queue \
  --location=$REGION \
  --max-dispatches-per-second=10 \
  --max-concurrent-dispatches=100 \
  --project=$PROJECT_ID \
  || echo "Compose queue already exists"

echo "✅ Queues created"
echo ""

# 2. Deploy OCR Worker
echo "🔍 Deploying OCR Worker..."
gcloud builds submit --tag gcr.io/$PROJECT_ID/documentai-ocr-worker \
  --file=workers/ocr/Dockerfile \
  --project=$PROJECT_ID

gcloud run deploy documentai-ocr-worker \
  --image gcr.io/$PROJECT_ID/documentai-ocr-worker \
  --platform managed \
  --region $REGION \
  --no-allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 600 \
  --max-instances 10 \
  --set-env-vars "DATABASE_URL=$DATABASE_URL" \
  --set-env-vars "STORAGE_BACKEND=$STORAGE_BACKEND" \
  --set-env-vars "GCS_BUCKET_NAME=$GCS_BUCKET_NAME" \
  --set-env-vars "SUPABASE_URL=$SUPABASE_URL" \
  --set-env-vars "SUPABASE_SERVICE_ROLE_KEY=$SUPABASE_SERVICE_ROLE_KEY" \
  --set-env-vars "OCR_BACKEND=local" \
  --project=$PROJECT_ID

OCR_WORKER_URL=$(gcloud run services describe documentai-ocr-worker \
  --region $REGION \
  --format 'value(status.url)' \
  --project=$PROJECT_ID)

echo "✅ OCR Worker deployed: $OCR_WORKER_URL"
echo ""

# 3. Deploy PDF Composer Worker
echo "📄 Deploying PDF Composer Worker..."
gcloud builds submit --tag gcr.io/$PROJECT_ID/documentai-composer-worker \
  --file=workers/composer/Dockerfile \
  --project=$PROJECT_ID

gcloud run deploy documentai-composer-worker \
  --image gcr.io/$PROJECT_ID/documentai-composer-worker \
  --platform managed \
  --region $REGION \
  --no-allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 10 \
  --set-env-vars "DATABASE_URL=$DATABASE_URL" \
  --set-env-vars "STORAGE_BACKEND=$STORAGE_BACKEND" \
  --set-env-vars "GCS_BUCKET_NAME=$GCS_BUCKET_NAME" \
  --set-env-vars "SUPABASE_URL=$SUPABASE_URL" \
  --set-env-vars "SUPABASE_SERVICE_ROLE_KEY=$SUPABASE_SERVICE_ROLE_KEY" \
  --project=$PROJECT_ID

COMPOSER_WORKER_URL=$(gcloud run services describe documentai-composer-worker \
  --region $REGION \
  --format 'value(status.url)' \
  --project=$PROJECT_ID)

echo "✅ Composer Worker deployed: $COMPOSER_WORKER_URL"
echo ""

# 4. Deploy API
echo "🌐 Deploying API..."
gcloud builds submit --tag gcr.io/$PROJECT_ID/documentai-api \
  --file=Dockerfile \
  --project=$PROJECT_ID

gcloud run deploy documentai-api \
  --image gcr.io/$PROJECT_ID/documentai-api \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 10 \
  --set-env-vars "DATABASE_URL=$DATABASE_URL" \
  --set-env-vars "STORAGE_BACKEND=$STORAGE_BACKEND" \
  --set-env-vars "GCS_BUCKET_NAME=$GCS_BUCKET_NAME" \
  --set-env-vars "SUPABASE_URL=$SUPABASE_URL" \
  --set-env-vars "SUPABASE_SERVICE_ROLE_KEY=$SUPABASE_SERVICE_ROLE_KEY" \
  --set-env-vars "GCP_PROJECT_ID=$PROJECT_ID" \
  --set-env-vars "GCP_REGION=$REGION" \
  --set-env-vars "OCR_WORKER_URL=$OCR_WORKER_URL" \
  --set-env-vars "COMPOSER_WORKER_URL=$COMPOSER_WORKER_URL" \
  --set-env-vars "ENVIRONMENT=production" \
  --project=$PROJECT_ID

API_URL=$(gcloud run services describe documentai-api \
  --region $REGION \
  --format 'value(status.url)' \
  --project=$PROJECT_ID)

echo "✅ API deployed: $API_URL"
echo ""

# 5. Grant permissions for Cloud Tasks to invoke workers
echo "🔐 Setting up IAM permissions..."
SERVICE_ACCOUNT=$(gcloud iam service-accounts list \
  --filter="email:$PROJECT_ID@appspot.gserviceaccount.com" \
  --format="value(email)" \
  --project=$PROJECT_ID)

gcloud run services add-iam-policy-binding documentai-ocr-worker \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/run.invoker" \
  --region=$REGION \
  --project=$PROJECT_ID

gcloud run services add-iam-policy-binding documentai-composer-worker \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/run.invoker" \
  --region=$REGION \
  --project=$PROJECT_ID

echo "✅ Permissions configured"
echo ""

echo "🎉 Deployment complete!"
echo ""
echo "API URL: $API_URL"
echo "OCR Worker: $OCR_WORKER_URL"
echo "Composer Worker: $COMPOSER_WORKER_URL"
echo ""
echo "Test the API:"
echo "curl $API_URL/api/v1/health"
