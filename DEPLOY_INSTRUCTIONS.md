# 🚀 Deploy to GCP - Quick Instructions

## Step 1: Get Supabase Service Role Key

1. Go to: https://supabase.com/dashboard/project/iixekrmukkpdmmqoheed/settings/api
2. Scroll down to "Project API keys"
3. Copy the **service_role** key (NOT the anon key!)
4. It should start with `eyJ...`

## Step 2: Deploy API to Cloud Run

```bash
# Set the service role key you just copied
export SUPABASE_SERVICE_ROLE_KEY="paste-your-key-here"

# Deploy API
gcloud run deploy documentai-api \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --set-env-vars "DATABASE_URL=postgresql://postgres:OyBok9Gt9664d92o@db.iixekrmukkpdmmqoheed.supabase.co:5432/postgres" \
  --set-env-vars "STORAGE_BACKEND=supabase" \
  --set-env-vars "SUPABASE_URL=https://iixekrmukkpdmmqoheed.supabase.co" \
  --set-env-vars "SUPABASE_SERVICE_ROLE_KEY=$SUPABASE_SERVICE_ROLE_KEY" \
  --set-env-vars "SUPABASE_BUCKET_NAME=documentai-storage" \
  --set-env-vars "GCP_PROJECT_ID=insta-440409" \
  --set-env-vars "GCP_REGION=us-central1" \
  --set-env-vars "ENVIRONMENT=production" \
  --set-env-vars "OCR_BACKEND=local" \
  --project=insta-440409
```

## Step 3: Get API URL

```bash
gcloud run services describe documentai-api \
  --region us-central1 \
  --format 'value(status.url)' \
  --project=insta-440409
```

## Step 4: Test API

```bash
# Save the URL
API_URL="your-api-url-from-step-3"

# Test health endpoint
curl $API_URL/api/v1/health
```

## Expected Output:
```json
{"status":"ok"}
```

## Next: Deploy Workers (Optional for Now)

Workers can be deployed later when you need OCR functionality.
For now, the API is deployed and ready for SwiftUI integration!

---

**Once you have the service role key, run the deploy command above!**
