# Vision Field Detection Worker

This worker performs vision-based form field detection for PDFs that do not have native AcroForm fields.

## How It Works

1. **Render PDF Pages**: Each page is rendered to a high-resolution image (150-200 DPI)
2. **Vision AI Analysis**: The image is sent to a multimodal LLM (GPT-4o-mini or Gemini Flash)
3. **Field Detection**: The AI detects form fields, checkboxes, signature areas, etc.
4. **Coordinate Normalization**: Bounding boxes are converted from 0-1000 to normalized 0-1 coordinates
5. **Database Storage**: Detected fields are saved to the `field_regions` table

## Coordinate System

### Vision Model Output
- Origin: (0, 0) = bottom-left corner
- Range: (1000, 1000) = top-right corner
- Format: `[x_min, y_min, x_max, y_max]`

### Database Storage
- Normalized coordinates (0-1 range)
- `x, y`: bottom-left corner of field
- `width, height`: dimensions of field

### Conversion Formula
```python
x = x_min / 1000.0
y = y_min / 1000.0
width = (x_max - x_min) / 1000.0
height = (y_max - y_min) / 1000.0
```

## Supported Providers

### OpenAI GPT-4o-mini
- Model: `gpt-4o-mini`
- API Key: Set `OPENAI_API_KEY` environment variable
- Cost: ~$0.15 per 1M input tokens, ~$0.60 per 1M output tokens

### Google Gemini Flash
- Model: `gemini-1.5-flash`
- API Key: Set `GEMINI_API_KEY` environment variable
- Cost: Free tier available, then ~$0.075 per 1M input tokens

## API Endpoints

### POST /detect
Detect form fields in a document.

**Request:**
```json
{
  "document_id": "uuid-string",
  "provider": "openai",  // or "gemini"
  "force": false  // re-process if fields exist
}
```

**Response:**
```json
{
  "document_id": "uuid-string",
  "status": "success",
  "page_count": 3,
  "fields_found": 15
}
```

### GET /health
Health check endpoint.

## Local Development

### Setup
```bash
cd document-ai-fastapi/workers/vision
pip install -r requirements.txt
```

### Environment Variables
```bash
export OPENAI_API_KEY="sk-..."
export GEMINI_API_KEY="..."
export DATABASE_URL="postgresql://..."
export STORAGE_BACKEND="supabase"
export SUPABASE_URL="https://..."
export SUPABASE_SERVICE_ROLE_KEY="..."
```

### Run Locally
```bash
python main.py
```

The service will start on port 8081.

### Test
```bash
# Test with OpenAI
curl -X POST http://localhost:8081/detect \
  -H "Content-Type: application/json" \
  -d '{"document_id": "your-doc-id", "provider": "openai"}'

# Test with Gemini
curl -X POST http://localhost:8081/detect \
  -H "Content-Type: application/json" \
  -d '{"document_id": "your-doc-id", "provider": "gemini"}'
```

## Deployment to Cloud Run

### Build and Deploy
```bash
# Set variables
export PROJECT_ID="your-gcp-project"
export REGION="us-central1"
export SERVICE_NAME="documentai-vision-worker"

# Build image
gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME

# Deploy to Cloud Run
gcloud run deploy $SERVICE_NAME \
  --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars "OPENAI_API_KEY=$OPENAI_API_KEY,DATABASE_URL=$DATABASE_URL,STORAGE_BACKEND=gcs,GCS_BUCKET_NAME=$BUCKET_NAME" \
  --memory 2Gi \
  --timeout 600
```

### Environment Variables for Cloud Run
- `OPENAI_API_KEY` - OpenAI API key
- `GEMINI_API_KEY` - Google Gemini API key (optional)
- `DATABASE_URL` - PostgreSQL connection string
- `STORAGE_BACKEND` - Storage backend (gcs, s3, supabase)
- `GCS_BUCKET_NAME` - GCS bucket name (if using GCS)
- `SUPABASE_URL` - Supabase URL (if using Supabase)
- `SUPABASE_SERVICE_ROLE_KEY` - Supabase service role key (if using Supabase)

## Integration with Main API

The main API can trigger vision detection via Cloud Tasks:

```python
from app.services.cloud_tasks import create_task

# Create task for vision detection
await create_task(
    queue_name="vision-queue",
    url=f"{settings.vision_worker_url}/detect",
    payload={
        "document_id": str(document_id),
        "provider": "openai",
        "force": False
    }
)
```

## Field Types Detected

The vision model can detect the following field types:
- `text` - Single-line text input
- `textarea` - Multi-line text input
- `checkbox` - Checkbox or radio button
- `signature` - Signature field
- `date` - Date input field
- `number` - Numeric input field
- `unknown` - Unclassified field

## Performance

- **Processing Time**: ~2-5 seconds per page (depends on provider and image size)
- **Accuracy**: ~85-95% field detection rate (varies by form complexity)
- **Cost**: ~$0.01-0.05 per document (depends on page count and provider)

## Troubleshooting

### API Key Not Found
Ensure environment variables are set:
```bash
echo $OPENAI_API_KEY
echo $GEMINI_API_KEY
```

### Database Connection Error
Check `DATABASE_URL` format:
```
postgresql://user:password@host:port/database
```

### Storage Error
Verify storage configuration and credentials are correct.

### Low Detection Accuracy
- Increase DPI (default 150, try 200)
- Use higher quality PDF source
- Try different provider (OpenAI vs Gemini)
- Adjust vision prompt for specific form types

## Future Enhancements

- [ ] Support for custom vision prompts per document type
- [ ] Batch processing for multiple documents
- [ ] Field grouping and relationship detection
- [ ] Template learning from user corrections
- [ ] Support for additional vision models (Claude, etc.)
