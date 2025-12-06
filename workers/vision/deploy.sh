#!/bin/bash

# Deploy Vision Field Detection Worker to Cloud Run

set -e

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-your-project-id}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="documentai-vision-worker"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"

echo "=========================================="
echo "Deploying Vision Worker to Cloud Run"
echo "=========================================="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"
echo "=========================================="

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI not found. Please install it first."
    exit 1
fi

# Check if logged in
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" &> /dev/null; then
    echo "❌ Not logged in to gcloud. Run: gcloud auth login"
    exit 1
fi

# Set project
echo "Setting project..."
gcloud config set project $PROJECT_ID

# Build image
echo "Building Docker image..."
gcloud builds submit --tag $IMAGE_NAME \
    --project $PROJECT_ID \
    .

# Deploy to Cloud Run
echo "Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_NAME \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 600 \
    --max-instances 10 \
    --set-env-vars "$(cat .env.production | grep -v '^#' | xargs | tr ' ' ',')" \
    --project $PROJECT_ID

# Get service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
    --platform managed \
    --region $REGION \
    --format 'value(status.url)' \
    --project $PROJECT_ID)

echo "=========================================="
echo "✅ Deployment complete!"
echo "=========================================="
echo "Service URL: $SERVICE_URL"
echo "Health check: $SERVICE_URL/health"
echo "=========================================="
echo ""
echo "Test the service:"
echo "curl -X POST $SERVICE_URL/detect \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"document_id\": \"your-doc-id\", \"provider\": \"openai\"}'"
echo ""
