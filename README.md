# DocumentAI Backend

Production-ready FastAPI backend for document OCR and form filling with PaddleOCR workers. Built for SwiftUI MVVM client integration.

## 🎯 Features

- **Document Upload**: PDF and image support with progress tracking
- **OCR Processing**: PaddleOCR-based field detection and extraction
- **Dynamic Forms**: Auto-generated form schemas for SwiftUI rendering
- **PDF Composition**: Burn user values into original PDFs
- **Cloud Storage**: GCS or S3-compatible storage abstraction
- **Async Workers**: Celery-based job processing
- **Production Ready**: Docker, Terraform, GCP Cloud Run deployment

## 🏗️ Architecture

- **API**: FastAPI + Uvicorn (GCP Cloud Run)
- **Database**: PostgreSQL + SQLAlchemy 2.x + Alembic
- **Workers**: Celery + Redis (GCP VM / Modal.com)
- **OCR**: PaddleOCR with GPU support
- **Storage**: GCS or S3-compatible (Cloudflare R2)
- **PDF**: PyMuPDF (fitz) for composition

## 🚀 Quick Start

```bash
# One-command setup
./scripts/quickstart.sh

# Or manually:
pip install -r requirements.txt
cp .env.example .env
docker-compose up -d
alembic upgrade head
python scripts/init_db.py

# Start services
make dev      # Terminal 1: API server
make worker   # Terminal 2: Celery worker
```

Visit http://localhost:8080/docs for interactive API documentation.

## 📋 API Flow

The backend supports this exact SwiftUI workflow:

1. **Upload**: `POST /api/v1/documents/init-upload` → Get `documentId`
2. **Process**: `POST /api/v1/documents/{id}/process` → Start OCR
3. **Poll**: `GET /api/v1/documents/{id}` → Wait for `status: "ready"`
4. **Receive**: Get `components[]` and `fieldMap{}` for dynamic UI
5. **Fill**: User fills form in SwiftUI
6. **Submit**: `POST /api/v1/documents/{id}/values` → Save values
7. **Compose**: `POST /api/v1/documents/{id}/compose` → Generate PDF
8. **Download**: `GET /api/v1/documents/{id}/download` → Get filled PDF URL

See [SWIFTUI_INTEGRATION.md](SWIFTUI_INTEGRATION.md) for complete client code.

## 🌐 Deployment

### GCP Cloud Run (Recommended)

```bash
# Automated with Terraform
cd deployment/terraform
terraform init
terraform apply -var="project_id=your-project-id"

# Or manual deployment
./deployment/gcp-deploy.sh
```

### Workers

**Option 1: GCP VM**
```bash
gcloud compute instances create documentai-worker \
  --metadata-from-file startup-script=deployment/worker-startup.sh
```

**Option 2: Modal.com** (Serverless GPU)
```bash
modal deploy deployment/modal_worker.py
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed instructions.

## 📁 Project Structure

```
app/
├── main.py              # FastAPI application
├── config.py            # Settings and environment
├── database.py          # SQLAlchemy setup
├── models/              # Database models
│   ├── document.py
│   ├── field.py
│   └── user.py
├── schemas/             # Pydantic models (camelCase for Swift)
│   ├── document.py
│   ├── field.py
│   └── common.py
├── routers/             # API endpoints
│   ├── documents.py
│   └── health.py
├── services/            # Business logic
│   ├── storage.py       # GCS/S3 abstraction
│   ├── ocr_dispatcher.py # OCR backend routing
│   ├── pdf_compose.py   # PDF generation
│   └── usage_tracker.py
├── workers/             # Celery tasks
│   ├── celery_app.py
│   └── tasks.py
└── utils/               # Helpers

deployment/
├── terraform/           # Infrastructure as code
├── gcp-deploy.sh       # Deployment script
├── modal_worker.py     # Modal.com OCR worker
└── cloudbuild.yaml     # CI/CD configuration

tests/                   # Unit and integration tests
```

## 🧪 Testing

```bash
# Run tests
make test

# Test OCR locally
python scripts/test_ocr.py sample.pdf

# Manual API testing
curl http://localhost:8080/api/v1/health
```

## 🔧 Configuration

Key environment variables (see `.env.example`):

```bash
# Database
DATABASE_URL=postgresql://user:pass@host/db

# Storage
STORAGE_BACKEND=gcs  # or s3
GCS_BUCKET_NAME=your-bucket

# OCR
OCR_BACKEND=local  # local, gcp, or modal

# Workers
CELERY_BROKER_URL=redis://localhost:6379/0
```

## 📊 Database Schema

- **users**: User accounts (single-user stub for now)
- **documents**: Uploaded files and processing status
- **field_regions**: Detected form fields with coordinates
- **field_values**: User-entered values
- **usage_events**: Metering and analytics

## 🔐 Security

- JWT-ready authentication (stub implementation)
- Secret Manager for credentials
- CORS configured for iOS/web clients
- Pre-signed URLs for storage access
- SQL injection protection via SQLAlchemy

## 📈 Monitoring

```bash
# Cloud Run logs
gcloud logging read "resource.type=cloud_run_revision" --limit 50

# Worker health
celery -A app.workers.celery_app inspect active

# Database queries
# Enable SQLAlchemy logging in config.py
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `make test`
5. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details

## 🆘 Support

- Documentation: See `DEPLOYMENT.md` and `SWIFTUI_INTEGRATION.md`
- Issues: GitHub Issues
- API Docs: `/docs` endpoint when running

## 🎯 Roadmap

- [ ] Template reuse for common forms
- [ ] Multi-user authentication
- [ ] Webhook notifications
- [ ] Batch processing
- [ ] Advanced field classification (ML)
- [ ] Real-time collaboration
- [ ] Mobile SDK
