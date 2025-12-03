# 🚀 Deployment Checklist

## Pre-Deployment

### ✅ Already Done
- [x] Supabase database connected
- [x] Database tables created
- [x] Default user created
- [x] Code refactored to Cloud Tasks
- [x] Workers separated into HTTP services
- [x] Deployment scripts created

### ⏳ Need to Do

#### 1. GCP Project Setup
- [ ] Create GCP project (or use existing)
- [ ] Enable billing
- [ ] Install gcloud CLI
- [ ] Authenticate: `gcloud auth login`

#### 2. Get Supabase Service Role Key
- [ ] Go to: https://supabase.com/dashboard/project/iixekrmukkpdmmqoheed/settings/api
- [ ] Copy **service_role** key (NOT anon key)
- [ ] Save it securely

#### 3. Configure Environment
```bash
# Set these variables
export GCP_PROJECT_ID="your-project-id"
export GCP_REGION="us-central1"
export DATABASE_URL="postgresql://postgres:OyBok9Gt9664d92o@db.iixekrmukkpdmmqoheed.supabase.co:5432/postgres"
export SUPABASE_URL="https://iixekrmukkpdmmqoheed.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="your-service-role-key"
export SUPABASE_BUCKET_NAME="documentai-storage"
export STORAGE_BACKEND="supabase"
```

#### 4. Enable GCP APIs
```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  cloudtasks.googleapis.com \
  --project=$GCP_PROJECT_ID
```

#### 5. Create Supabase Storage Bucket
- [ ] Go to: https://supabase.com/dashboard/project/iixekrmukkpdmmqoheed/storage/buckets
- [ ] Create bucket: `documentai-storage`
- [ ] Set to **Private**

## Deployment

### Run Deployment Script
```bash
# Make executable
chmod +x deployment/gcp/deploy-all.sh

# Deploy everything
./deployment/gcp/deploy-all.sh
```

This will:
1. Create Cloud Task queues
2. Build and deploy OCR worker
3. Build and deploy Composer worker
4. Build and deploy API
5. Configure IAM permissions

Expected time: 10-15 minutes

## Post-Deployment Testing

### 1. Test Health Endpoint
```bash
API_URL=$(gcloud run services describe documentai-api \
  --region $GCP_REGION \
  --format 'value(status.url)' \
  --project=$GCP_PROJECT_ID)

curl $API_URL/api/v1/health
# Expected: {"status":"ok"}
```

### 2. Test Document Upload
```bash
# Create test PDF
echo "%PDF-1.4" > test.pdf

# Upload
curl -X POST $API_URL/api/v1/documents/init-upload \
  -F "file=@test.pdf" \
  | jq

# Save documentId from response
```

### 3. Test OCR Processing
```bash
# Replace with your documentId
DOC_ID="your-document-id"

# Start processing
curl -X POST $API_URL/api/v1/documents/$DOC_ID/process

# Check status (wait 10-30 seconds)
curl $API_URL/api/v1/documents/$DOC_ID | jq
```

### 4. Test Full Workflow
```bash
# Submit values
curl -X POST $API_URL/api/v1/documents/$DOC_ID/values \
  -H "Content-Type: application/json" \
  -d '{"values": [{"fieldRegionId": "uuid", "value": "test", "source": "manual"}]}'

# Compose PDF
curl -X POST $API_URL/api/v1/documents/$DOC_ID/compose

# Wait 10 seconds, then download
curl $API_URL/api/v1/documents/$DOC_ID/download | jq
```

## Verify Deployment

### Check Services
```bash
# List Cloud Run services
gcloud run services list --region=$GCP_REGION

# Should see:
# - documentai-api
# - documentai-ocr-worker
# - documentai-composer-worker
```

### Check Cloud Tasks
```bash
# List queues
gcloud tasks queues list --location=$GCP_REGION

# Should see:
# - ocr-queue
# - compose-queue
```

### Check Logs
```bash
# API logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=documentai-api" --limit 10

# OCR worker logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=documentai-ocr-worker" --limit 10
```

## SwiftUI Integration

### Update API Base URL
```swift
// In your SwiftUI app
let API_BASE_URL = "YOUR_API_URL_HERE/api/v1"

// Example:
// let API_BASE_URL = "https://documentai-api-abc123-uc.a.run.app/api/v1"
```

### Test from iOS
1. Update base URL in DocumentAIService
2. Run app on simulator or device
3. Upload a test document
4. Verify OCR processing
5. Fill form and generate PDF
6. Download and view filled PDF

## Monitoring

### View Metrics
- Go to: https://console.cloud.google.com/run
- Select each service
- View metrics: requests, latency, errors

### Set Up Alerts (Optional)
```bash
# Alert on errors
gcloud alpha monitoring policies create \
  --notification-channels=YOUR_CHANNEL \
  --display-name="DocumentAI Errors" \
  --condition-display-name="Error rate > 5%" \
  --condition-threshold-value=0.05
```

## Cost Monitoring

### Check Current Costs
- Go to: https://console.cloud.google.com/billing
- View by service
- Should be RM0-5/month for solo user

### Set Budget Alert
```bash
# Set RM50/month budget
gcloud billing budgets create \
  --billing-account=YOUR_BILLING_ACCOUNT \
  --display-name="DocumentAI Budget" \
  --budget-amount=50MYR \
  --threshold-rule=percent=50 \
  --threshold-rule=percent=90 \
  --threshold-rule=percent=100
```

## Troubleshooting

### Deployment Fails
- Check gcloud authentication: `gcloud auth list`
- Verify project ID: `gcloud config get-value project`
- Check enabled APIs: `gcloud services list --enabled`

### Workers Not Invoked
- Check IAM permissions
- Verify Cloud Tasks queues exist
- Check worker URLs in API environment variables

### Database Connection Issues
- Verify DATABASE_URL is correct
- Test connection from Cloud Shell
- Check Supabase project is active

## Success Criteria

- [ ] All 3 Cloud Run services deployed
- [ ] Health endpoint returns 200
- [ ] Document upload works
- [ ] OCR processing completes
- [ ] PDF composition works
- [ ] Download URL is generated
- [ ] SwiftUI app can connect
- [ ] Costs within budget (RM0-5/month)

## Next Steps After Deployment

1. ✅ Test all endpoints thoroughly
2. ✅ Integrate with SwiftUI app
3. ✅ Monitor logs and metrics
4. ✅ Set up alerts
5. ✅ Document API URL for team
6. ✅ Plan for scaling if needed

---

**Ready to deploy? Run: `./deployment/gcp/deploy-all.sh`** 🚀
