# DocumentAI Backend

Production-ready FastAPI backend for document OCR and form filling with PaddleOCR workers. Built for SwiftUI MVVM client integration.

## Features

- **Document Upload**: PDF and image support with progress tracking
- **OCR Processing**: PaddleOCR-based field detection and extraction
- **Dynamic Forms**: Auto-generated form schemas for SwiftUI rendering
- **PDF Composition**: Burn user values into original PDFs
- **Cloud Storage**: Supabase Storage integration
- **Async Workers**: Cloud Tasks-based job processing
- **Production Ready**: Docker, GCP Cloud Run deployment

## Quick Start

### Prerequisites
- Python 3.11+
- Supabase account (free tier works)

### Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Supabase credentials

# Run migrations
alembic upgrade head
python scripts/init_db.py

# Start API
uvicorn app.main:app --reload --port 8080
```

### Test

```bash
curl http://localhost:8080/api/v1/health
# Expected: {"status":"ok"}

# View API docs
open http://localhost:8080/docs
```

## API Flow

1. **Upload**: `POST /api/v1/documents/init-upload` → Get `documentId`
2. **Process**: `POST /api/v1/documents/{id}/process` → Start OCR
3. **Poll**: `GET /api/v1/documents/{id}` → Wait for `status: "ready"`
4. **Fill**: User fills form in SwiftUI
5. **Submit**: `POST /api/v1/documents/{id}/values` → Save values
6. **Compose**: `POST /api/v1/documents/{id}/compose` → Generate PDF
7. **Download**: `GET /api/v1/documents/{id}/download` → Get filled PDF URL

## Project Structure

```
app/
├── main.py              # FastAPI application
├── config.py            # Settings and environment
├── database.py          # SQLAlchemy setup
├── models/              # Database models
├── schemas/             # Pydantic models (camelCase for Swift)
├── routers/             # API endpoints
├── services/            # Business logic
└── utils/               # Helpers

workers/
├── ocr/                 # OCR worker service
└── composer/            # PDF composition worker

deployment/
├── gcp/                 # GCP deployment scripts
└── terraform/           # Infrastructure as code
```

## Deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for GCP Cloud Run deployment.

```bash
# Quick deploy
./deployment/gcp/deploy-all.sh
```

## Documentation

- [API Reference](docs/API.md) - Complete endpoint documentation
- [Architecture](docs/ARCHITECTURE.md) - System design and diagrams
- [Deployment](docs/DEPLOYMENT.md) - GCP deployment guide
- [SwiftUI Integration](docs/SWIFTUI_INTEGRATION.md) - iOS client guide

## Configuration

Key environment variables (see `.env.example`):

```bash
DATABASE_URL=postgresql://user:pass@host/db
STORAGE_BACKEND=supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-key
SUPABASE_BUCKET_NAME=documentai-storage
```

## Testing

```bash
pytest tests/
```

## License

MIT License
