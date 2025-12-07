# CommonForms Worker

Cloud Run worker service for processing PDFs with CommonForms library.

## What it does

1. Downloads original PDF from Supabase Storage
2. Runs CommonForms `prepare_form()` to detect fields and generate fillable PDF
3. Uploads fillable PDF to Supabase Storage
4. Saves field metadata to database
5. Updates document status

## Local Development

```bash
# From document-ai-fastapi directory
cd workers
python cf_worker.py
```

Worker runs on port 8081 by default.

## API Endpoints

### POST /process-commonforms

Process a document with CommonForms.

Request:
```json
{
  "document_id": "uuid",
  "job_id": "uuid"
}
```

Response:
```json
{
  "job_id": "uuid",
  "document_id": "uuid",
  "status": "completed",
  "output_pdf_url": "https://...",
  "fields": [
    {
      "id": "uuid",
      "type": "text",
      "page": 0,
      "bbox": [x1, y1, x2, y2],
      "label": "Field Name"
    }
  ]
}
```

### GET /health

Health check endpoint.

## Deployment

Build and deploy to Cloud Run:

```bash
gcloud builds submit --config=workers/cf/cloudbuild.yaml
```

## Environment Variables

- `DATABASE_URL` - PostgreSQL connection string
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_SERVICE_ROLE_KEY` - Supabase service role key
- `SUPABASE_BUCKET_NAME` - Storage bucket name
- `STORAGE_BACKEND` - Set to "supabase"
