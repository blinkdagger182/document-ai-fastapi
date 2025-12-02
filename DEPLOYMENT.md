# DocumentAI Backend - Deployment Guide

## Prerequisites

- GCP account with billing enabled
- `gcloud` CLI installed and configured
- Docker installed
- Python 3.11+

## Local Development

### 1. Setup Environment

```bash
# Clone repository
git clone <your-repo>
cd documentai-backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env
# Edit .env with your configuration
```

### 2. Start Services with Docker Compose

```bash
# Start PostgreSQL and Redis
docker-compose up -d postgres redis

# Run migrations
alembic upgrade head

# Initialize database with default user
python scripts/init_db.py
```

### 3. Run API Server

```bash
# Terminal 1: API server
uvicorn app.main:app --reload --port 8080

# Terminal 2: Celery worker
celery -A app.workers.celery_app worker -Q ocr,compose --loglevel=info
```

### 4. Test the API

```bash
# Health check
curl http://localhost:8080/api/v1/health

# View API docs
open http://localhost:8080/docs
```

## GCP Deployment

### Option 1: Automated Deployment with Terraform

```bash
cd deployment/terraform

# Initialize Terraform
terraform init

# Review plan
terraform plan -var="project_id=your-gcp-project-id"

# Apply infrastructure
terraform apply -var="project_id=your-gcp-project-id"
```

### Option 2: Manual Deployment

#### Step 1: Setup GCP Project

```bash
export PROJECT_ID="your-project-id"
export REGION="us-central1"

gcloud config set project $PROJECT_ID
```

#### Step 2: Create Cloud SQL Database

```bash
# Create PostgreSQL instance
gcloud sql instances create documentai-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=$REGION

# Create database
gcloud sql databases create documentai \
  --instance=documentai-db

# Set password
gcloud sql users set-password postgres \
  --instance=documentai-db \
  --password=YOUR_SECURE_PASSWORD
```

#### Step 3: Create Cloud Storage Bucket

```bash
gsutil mb -l $REGION gs://$PROJECT_ID-documentai-storage
gsutil cors set deployment/cors.json gs://$PROJECT_ID-documentai-storage
```

#### Step 4: Create Redis Instance

```bash
gcloud redis instances create documentai-redis \
  --size=1 \
  --region=$REGION \
  --redis-version=redis_7_0
```

#### Step 5: Store Secrets

```bash
# Database URL
echo -n "postgresql://postgres:PASSWORD@/documentai?host=/cloudsql/PROJECT:REGION:documentai-db" | \
  gcloud secrets create documentai-db-url --data-file=-

# Redis URL
REDIS_HOST=$(gcloud redis instances describe documentai-redis --region=$REGION --format="value(host)")
echo -n "redis://$REDIS_HOST:6379/0" | \
  gcloud secrets create documentai-redis-url --data-file=-

# Bucket name
echo -n "$PROJECT_ID-documentai-storage" | \
  gcloud secrets create documentai-bucket --data-file=-
```

#### Step 6: Deploy API to Cloud Run

```bash
# Build and deploy
gcloud builds submit --tag gcr.io/$PROJECT_ID/documentai-api

gcloud run deploy documentai-api \
  --image gcr.io/$PROJECT_ID/documentai-api \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars "ENVIRONMENT=production,STORAGE_BACKEND=gcs,OCR_BACKEND=local" \
  --set-secrets "DATABASE_URL=documentai-db-url:latest,REDIS_URL=documentai-redis-url:latest,GCS_BUCKET_NAME=documentai-bucket:latest" \
  --add-cloudsql-instances $PROJECT_ID:$REGION:documentai-db \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --max-instances 10
```

#### Step 7: Deploy Workers to GCP VM

```bash
# Create VM with startup script
gcloud compute instances create documentai-worker-1 \
  --zone=$REGION-a \
  --machine-type=n1-standard-2 \
  --image-family=debian-11 \
  --image-project=debian-cloud \
  --metadata-from-file startup-script=deployment/worker-startup.sh \
  --scopes=cloud-platform

# Or use Container-Optimized OS
gcloud compute instances create-with-container documentai-worker-1 \
  --zone=$REGION-a \
  --machine-type=n1-standard-2 \
  --container-image=gcr.io/$PROJECT_ID/documentai-worker:latest \
  --container-env=DATABASE_URL=...,REDIS_URL=... \
  --scopes=cloud-platform
```

### Option 3: Deploy Workers to Modal.com

```bash
# Install Modal
pip install modal

# Setup Modal account
modal setup

# Deploy OCR worker
modal deploy deployment/modal_worker.py

# Get endpoint URL
modal app list

# Update .env with Modal endpoint
# OCR_BACKEND=modal
# MODAL_OCR_ENDPOINT=https://your-app.modal.run
```

## CI/CD with Cloud Build

### Setup Trigger

```bash
# Connect repository
gcloud builds triggers create github \
  --repo-name=documentai-backend \
  --repo-owner=your-org \
  --branch-pattern="^main$" \
  --build-config=deployment/cloudbuild.yaml
```

## Monitoring

### Cloud Run Logs

```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=documentai-api" --limit 50
```

### Worker Logs

```bash
gcloud compute ssh documentai-worker-1 --zone=$REGION-a
sudo journalctl -u celery -f
```

## Scaling

### API (Cloud Run)
- Auto-scales based on requests
- Configure max instances: `--max-instances=50`

### Workers
- Add more VM instances
- Use Managed Instance Groups for auto-scaling
- Or scale Modal.com workers automatically

## Cost Optimization

1. **Cloud Run**: Pay per request, scales to zero
2. **Cloud SQL**: Use smallest tier for dev, scale up for production
3. **Redis**: Use Memorystore Basic tier (1GB) for dev
4. **Storage**: GCS Standard class, lifecycle policies for old files
5. **Workers**: Use preemptible VMs or Modal.com pay-per-use

## Security Checklist

- [ ] Enable Cloud SQL SSL connections
- [ ] Use VPC for internal services
- [ ] Rotate secrets regularly
- [ ] Enable Cloud Armor for DDoS protection
- [ ] Set up IAM roles with least privilege
- [ ] Enable audit logging
- [ ] Use Secret Manager for all credentials
- [ ] Configure CORS properly for production domains

## Troubleshooting

### Database Connection Issues
```bash
# Test Cloud SQL connection
gcloud sql connect documentai-db --user=postgres
```

### Worker Not Processing Jobs
```bash
# Check Redis connection
redis-cli -h REDIS_HOST ping

# Check Celery queue
celery -A app.workers.celery_app inspect active
```

### Storage Upload Failures
```bash
# Check bucket permissions
gsutil iam get gs://$PROJECT_ID-documentai-storage
```
