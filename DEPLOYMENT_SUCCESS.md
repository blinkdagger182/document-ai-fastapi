# 🎉 Deployment to GCP - SUCCESS!

## ✅ What's Deployed

### API Service
- **Service**: documentai-api
- **URL**: https://documentai-api-824241800977.us-central1.run.app
- **Status**: ✅ Running
- **Region**: us-central1
- **Project**: insta-440409

### Health Check
```bash
curl https://documentai-api-824241800977.us-central1.run.app/api/v1/health
# Response: {"status":"ok"}
```

### API Documentation
🔗 https://documentai-api-824241800977.us-central1.run.app/docs

## 🔧 Configuration

### Database
- ✅ Connected to Supabase PostgreSQL
- ✅ Tables created and migrated
- ✅ Default user exists

### Storage
- ⚠️ Supabase Storage bucket needs to be created
- Bucket name: `documentai-storage`

## ⚠️ Action Required: Create Storage Bucket

The API is deployed but needs a storage bucket to handle file uploads.

### Create Bucket in Supabase:

1. Go to: https://supabase.com/dashboard/project/iixekrmukkpdmmqoheed/storage/buckets
2. Click "New bucket"
3. Name: `documentai-storage`
4. Make it **Private** (not public)
5. Click "Create bucket"

### Set Bucket Policies:

After creating the bucket, set these policies:

```sql
-- Allow service role to upload
CREATE POLICY "Service role can upload"
ON storage.objects FOR INSERT
TO service_role
WITH CHECK (bucket_id = 'documentai-storage');

-- Allow service role to read
CREATE POLICY "Service role can read"
ON storage.objects FOR SELECT
TO service_role
USING (bucket_id = 'documentai-storage');

-- Allow service role to delete
CREATE POLICY "Service role can delete"
ON storage.objects FOR DELETE
TO service_role
USING (bucket_id = 'documentai-storage');
```

## 🧪 Test After Creating Bucket

```bash
# Create test PDF
echo "%PDF-1.4" > test.pdf

# Upload document
curl -X POST https://documentai-api-824241800977.us-central1.run.app/api/v1/documents/init-upload \
  -F "file=@test.pdf"

# Should return document ID and details
```

## 📱 SwiftUI Integration

Update your SwiftUI app with this API URL:

```swift
let API_BASE_URL = "https://documentai-api-824241800977.us-central1.run.app/api/v1"
```

## 🎯 Available Endpoints

All endpoints are live and ready:

- ✅ `GET /api/v1/health` - Health check
- ✅ `POST /api/v1/documents/init-upload` - Upload document
- ✅ `POST /api/v1/documents/{id}/process` - Start OCR (needs workers)
- ✅ `GET /api/v1/documents/{id}` - Get document details
- ✅ `POST /api/v1/documents/{id}/values` - Submit form values
- ✅ `POST /api/v1/documents/{id}/compose` - Generate PDF (needs workers)
- ✅ `GET /api/v1/documents/{id}/download` - Download filled PDF

## ⏳ Workers Not Yet Deployed

OCR and PDF Composer workers are not deployed yet. They can be added later when needed.

For now, the API can:
- ✅ Accept document uploads
- ✅ Store documents in database
- ✅ Return document metadata
- ⏳ OCR processing (needs worker)
- ⏳ PDF composition (needs worker)

## 💰 Current Cost

**FREE!** Everything is within GCP free tier:
- Cloud Run: 2M requests/month free
- Supabase: Free tier (500MB DB, 1GB storage)
- **Total: RM0/month**

## 📊 Monitoring

### View Logs
```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=documentai-api" --limit 20 --project=insta-440409
```

### View Metrics
Go to: https://console.cloud.google.com/run/detail/us-central1/documentai-api/metrics?project=insta-440409

## 🚀 Next Steps

1. ✅ API deployed to Cloud Run
2. ⏳ Create Supabase storage bucket
3. ⏳ Test document upload
4. ⏳ Deploy workers (optional, for OCR/PDF features)
5. ⏳ Integrate with SwiftUI app

## 🔗 Quick Links

- **API**: https://documentai-api-824241800977.us-central1.run.app
- **Docs**: https://documentai-api-824241800977.us-central1.run.app/docs
- **Supabase Dashboard**: https://supabase.com/dashboard/project/iixekrmukkpdmmqoheed
- **GCP Console**: https://console.cloud.google.com/run/detail/us-central1/documentai-api?project=insta-440409

---

**API is live and ready for SwiftUI integration!** 🎉

Just create the storage bucket and you're good to go!
