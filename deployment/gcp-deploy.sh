#!/bin/bash
# Deployment script for GCP Cloud Run

set -e

PROJECT_ID=${GCP_PROJECT_ID:-"your-project-id"}
REGION=${GCP_REGION:-"us-central1"}
SERVICE_NAME="documentai-api"

echo "Deploying DocumentAI to GCP Cloud Run..."
echo "Project: $PROJECT_ID"
echo "Region: $REGION"

# Build and push API container
echo "Building API container..."
gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME .

# Deploy to Cloud Run
echo "Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars "ENVIRONMENT=production" \
  --set-secrets "DATABASE_URL=documentai-db-url:latest" \
  --set-secrets "REDIS_URL=documentai-redis-url:latest" \
  --set-secrets "GCS_BUCKET_NAME=documentai-bucket:latest" \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --max-instances 10

echo "Deployment complete!"
echo "Service URL:"
gcloud run services describe $SERVICE_NAME --region $REGION --format 'value(status.url)'
