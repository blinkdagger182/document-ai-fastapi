#!/bin/bash
set -e

# Configuration
export PROJECT_ID="insta-440409"
export REGION="us-central1"
export DATABASE_URL="postgresql://postgres:OyBok9Gt9664d92o@db.iixekrmukkpdmmqoheed.supabase.co:5432/postgres"
export SUPABASE_URL="https://iixekrmukkpdmmqoheed.supabase.co"
export STORAGE_BACKEND="supabase"
export SUPABASE_BUCKET_NAME="documentai-storage"

echo "🚀 Deploying DocumentAI to GCP"
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Get Supabase service role key from user
echo "⚠️  Need Supabase Service Role Key"
echo "Get it from: https://supabase.com/dashboard/project/iixekrmukkpdmmqoheed/settings/api"
echo ""
read -p "Enter Supabase Service Role Key: " SUPABASE_SERVICE_ROLE_KEY
export SUPABASE_SERVICE_ROLE_KEY

echo ""
echo "📋 Step 1: Creating Cloud Task queues..."
gcloud tasks queues create ocr-queue \
  --location=$REGION \
  --project=$PROJECT_ID \
  2>/dev/null || echo "  OCR queue already exists"

gcloud tasks queues create compose-queue \
  --location=$REGION \
  --project=$PROJECT_ID \
  2>/dev/null || echo "  Compose queue already exists"

echo "✅ Queues ready"
echo ""

# Deploy API first (lightweight, no OCR dependencies)
echo "🌐 Step 2: Deploying API..."
gcloud run deploy documentai-api \
  --source . \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 10 \
  --set-env-vars "DATABASE_URL=$DATABASE_URL" \
  --set-env-vars "STORAGE_BACKEND=$STORAGE_BACKEND" \
  --set-env-vars "SUPABASE_URL=$SUPABASE_URL" \
  --set-env-vars "SUPABASE_SERVICE_ROLE_KEY=$SUPABASE_SERVICE_ROLE_KEY" \
  --set-env-vars "SUPABASE_BUCKET_NAME=$SUPABASE_BUCKET_NAME" \
  --set-env-vars "GCP_PROJECT_ID=$PROJECT_ID" \
  --set-env-vars "GCP_REGION=$REGION" \
  --set-env-vars "ENVIRONMENT=production" \
  --set-env-vars "OCR_BACKEND=local" \
  --project=$PROJECT_ID

API_URL=$(gcloud run services describe documentai-api \
  --region $REGION \
  --format 'value(status.url)' \
  --project=$PROJECT_ID)

echo "✅ API deployed: $API_URL"
echo ""

echo "🧪 Step 3: Testing API..."
curl -s $API_URL/api/v1/health | jq || curl -s $API_URL/api/v1/health

echo ""
echo ""
echo "🎉 Deployment Complete!"
echo ""
echo "API URL: $API_URL"
echo ""
echo "Test commands:"
echo "  curl $API_URL/api/v1/health"
echo ""
echo "Next: Deploy workers (OCR and Composer) when needed"
echo "  They require larger containers with PaddleOCR/PyMuPDF"
