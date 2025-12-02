# DocumentAI Backend - Project Summary

## Overview

A production-ready FastAPI backend for document OCR and intelligent form filling, designed specifically for SwiftUI MVVM client integration. The system processes PDFs/images, extracts form fields using PaddleOCR, generates dynamic form schemas, and composes filled PDFs.

## Key Components

### 1. API Layer (FastAPI)
- **Location**: `app/main.py`, `app/routers/`
- **Features**:
  - RESTful endpoints with OpenAPI documentation
  - CORS-enabled for iOS/web clients
  - Multipart file upload with progress support
  - Async/await for non-blocking operations
  - Dependency injection for clean architecture

### 2. Database Layer (PostgreSQL + SQLAlchemy)
- **Location**: `app/models/`, `app/database.py`
- **Schema**:
  - `users`: User management (single-user stub, ready for multi-user)
  - `documents`: File metadata and processing status
  - `field_regions`: Detected form fields with normalized coordinates
  - `field_values`: User-entered values
  - `usage_events`: Metering and analytics
- **Migrations**: Alembic for version control

### 3. Worker Layer (Celery)
- **Location**: `app/workers/`
- **Tasks**:
  - `run_ocr`: Extract fields from documents using PaddleOCR
  - `compose_pdf`: Generate filled PDFs with PyMuPDF
- **Queues**: Separate queues for OCR and composition
- **Broker**: Redis for job distribution

### 4. Storage Abstraction
- **Location**: `app/services/storage.py`
- **Backends**:
  - Google Cloud Storage (GCS)
  - S3-compatible (Cloudflare R2, MinIO, etc.)
- **Features**:
  - Pre-signed URLs for secure downloads
  - Async upload/download
  - Environment-driven configuration

### 5. OCR Dispatcher
- **Location**: `app/services/ocr_dispatcher.py`
- **Backends**:
  - **Local**: PaddleOCR running in worker container
  - **GCP**: HTTP endpoint on GCP VM/Cloud Run
  - **Modal.com**: Serverless GPU workers
- **Features**:
  - Pluggable architecture
  - Normalized coordinate system [0,1]
  - Field type classification heuristics

### 6. PDF Composition
- **Location**: `app/services/pdf_compose.py`
- **Features**:
  - PyMuPDF (fitz) for PDF manipulation
  - Text overlay with adaptive font sizing
  - Checkbox rendering
  - Preserves original PDF structure

## Data Flow

```
1. SwiftUI Upload
   ↓
2. FastAPI receives file → Store in GCS/S3
   ↓
3. Create document record (status: imported)
   ↓
4. Enqueue OCR task → Celery worker
   ↓
5. Worker downloads file → Run PaddleOCR
   ↓
6. Extract text boxes → Classify field types
   ↓
7. Store field_regions → Update status: ready
   ↓
8. SwiftUI polls → Receives components + fieldMap
   ↓
9. User fills form → SwiftUI submits values
   ↓
10. Store field_values → Enqueue compose task
    ↓
11. Worker downloads original PDF
    ↓
12. Overlay values → Generate filled PDF
    ↓
13. Upload to storage → Update status: filled
    ↓
14. SwiftUI downloads → Pre-signed URL
```

## API Contract

### Response Format (camelCase for Swift)
All JSON responses use camelCase to match Swift coding conventions:
- `documentId` not `document_id`
- `fileName` not `file_name`
- `pageIndex` not `page_index`

### Status Progression
```
imported → processing → ready → filling → filled
                ↓
              failed
```

### Field Components
Dynamic form schema for SwiftUI rendering:
```json
{
  "id": "uuid",
  "fieldId": "uuid",
  "type": "text|multiline|checkbox|date|number|signature",
  "label": "Field Label",
  "placeholder": "Enter value",
  "pageIndex": 0
}
```

### Field Map
Coordinate data for PDF overlay visualization:
```json
{
  "field-uuid": {
    "x": 0.15,      // Normalized [0,1]
    "y": 0.25,
    "width": 0.4,
    "height": 0.03,
    "confidence": 0.95
  }
}
```

## Deployment Architecture

### Production Setup (GCP)

```
┌─────────────────┐
│  SwiftUI App    │
└────────┬────────┘
         │ HTTPS
         ↓
┌─────────────────┐
│  Cloud Run      │ ← FastAPI (auto-scaling)
│  (API)          │
└────┬────────┬───┘
     │        │
     │        └──────────┐
     ↓                   ↓
┌─────────────┐   ┌──────────────┐
│ Cloud SQL   │   │ Memorystore  │
│ (Postgres)  │   │ (Redis)      │
└─────────────┘   └──────┬───────┘
                         │
                         ↓
                  ┌──────────────┐
                  │  GCP VM      │ ← Celery Workers
                  │  or Modal    │   (PaddleOCR)
                  └──────┬───────┘
                         │
                         ↓
                  ┌──────────────┐
                  │  Cloud       │
                  │  Storage     │
                  └──────────────┘
```

### Cost Estimates (Monthly)

**Development**:
- Cloud Run: ~$5 (minimal traffic)
- Cloud SQL: ~$10 (db-f1-micro)
- Redis: ~$50 (1GB Basic)
- Storage: ~$1 (10GB)
- Workers: ~$20 (1 e2-small VM)
**Total: ~$86/month**

**Production** (1000 docs/month):
- Cloud Run: ~$50
- Cloud SQL: ~$100 (db-n1-standard-1)
- Redis: ~$100 (5GB Standard)
- Storage: ~$10 (100GB)
- Workers: ~$200 (3 n1-standard-2 VMs) or Modal.com pay-per-use
**Total: ~$460/month**

## Technology Choices

### Why FastAPI?
- Modern async/await support
- Automatic OpenAPI documentation
- Pydantic validation
- High performance (Starlette + Uvicorn)
- Easy deployment to Cloud Run

### Why Celery?
- Mature, battle-tested
- Flexible routing (queues, priorities)
- Retry mechanisms
- Monitoring tools (Flower)
- Works with Redis/RabbitMQ

### Why PaddleOCR?
- Open source, no API costs
- Multi-language support
- Good accuracy for forms
- Can run on CPU or GPU
- Active development

### Why PyMuPDF?
- Fast PDF manipulation
- Text overlay support
- Preserves PDF structure
- Python-native
- Well-documented

### Why PostgreSQL?
- ACID compliance
- JSON support for flexible schemas
- Full-text search capabilities
- Mature ecosystem
- Cloud SQL managed service

## Security Considerations

1. **Authentication**: JWT-ready, currently single-user stub
2. **Storage**: Pre-signed URLs, no public access
3. **Database**: Parameterized queries via SQLAlchemy
4. **Secrets**: Environment variables + Secret Manager
5. **CORS**: Configured for specific origins
6. **Input Validation**: Pydantic models
7. **File Upload**: Size limits, type validation
8. **SQL Injection**: ORM prevents direct SQL

## Performance Optimizations

1. **Async I/O**: FastAPI async endpoints
2. **Connection Pooling**: SQLAlchemy pool
3. **Caching**: Redis for session/cache
4. **CDN**: Cloud Storage for static files
5. **Lazy Loading**: Pagination for large lists
6. **Worker Concurrency**: Multiple Celery workers
7. **Database Indexes**: On foreign keys and status fields

## Testing Strategy

1. **Unit Tests**: `tests/test_api.py`
   - Endpoint validation
   - Mock external services
   - Database operations

2. **Integration Tests**: (TODO)
   - Full workflow tests
   - Storage integration
   - Worker tasks

3. **Load Tests**: (TODO)
   - Locust/k6 for API
   - Concurrent uploads
   - Worker throughput

## Monitoring & Observability

1. **Logs**: Structured logging to stdout
2. **Metrics**: Cloud Run metrics, Celery stats
3. **Tracing**: (TODO) OpenTelemetry
4. **Alerts**: (TODO) Cloud Monitoring
5. **Health Checks**: `/api/v1/health` endpoint

## Future Enhancements

### Phase 2
- [ ] Multi-user authentication (JWT)
- [ ] Template library for common forms
- [ ] Webhook notifications
- [ ] Batch processing API

### Phase 3
- [ ] ML-based field classification
- [ ] Auto-fill from user profile
- [ ] Real-time collaboration
- [ ] Mobile SDK (Swift Package)

### Phase 4
- [ ] Advanced OCR (handwriting)
- [ ] Multi-language support
- [ ] E-signature integration
- [ ] Audit trail and compliance

## Development Workflow

```bash
# Local development
make dev          # Start API
make worker       # Start worker
make test         # Run tests

# Docker development
make docker-up    # All services
make docker-down  # Stop all

# Deployment
make deploy-gcp   # Deploy to GCP
```

## File Organization

```
app/
├── main.py              # FastAPI app entry point
├── config.py            # Environment configuration
├── database.py          # SQLAlchemy setup
├── models/              # Database models (ORM)
├── schemas/             # Pydantic models (API)
├── routers/             # API endpoints
├── services/            # Business logic
├── workers/             # Celery tasks
└── utils/               # Helpers

deployment/
├── terraform/           # Infrastructure as code
├── gcp-deploy.sh       # Deployment script
├── modal_worker.py     # Serverless OCR
└── cloudbuild.yaml     # CI/CD

tests/                   # Unit and integration tests
scripts/                 # Utility scripts
alembic/                 # Database migrations
```

## Key Files

- `README.md`: Quick start and overview
- `API.md`: Complete API documentation
- `DEPLOYMENT.md`: Deployment guide
- `SWIFTUI_INTEGRATION.md`: Client integration
- `requirements.txt`: Python dependencies
- `.env.example`: Configuration template
- `docker-compose.yml`: Local development
- `Makefile`: Common commands

## Dependencies

**Core**:
- fastapi==0.109.0
- uvicorn==0.27.0
- sqlalchemy==2.0.25
- celery==5.3.6
- pydantic==2.5.3

**OCR/PDF**:
- paddleocr==2.7.0.3
- PyMuPDF==1.23.21

**Storage**:
- google-cloud-storage==2.14.0
- boto3==1.34.34

**Database**:
- psycopg2-binary==2.9.9
- alembic==1.13.1

## Environment Variables

See `.env.example` for complete list. Key variables:

```bash
DATABASE_URL              # PostgreSQL connection
REDIS_URL                 # Redis connection
STORAGE_BACKEND           # gcs or s3
OCR_BACKEND              # local, gcp, or modal
GCS_BUCKET_NAME          # Storage bucket
CORS_ORIGINS             # Allowed origins
```

## Support & Documentation

- **API Docs**: `/docs` endpoint (Swagger UI)
- **ReDoc**: `/redoc` endpoint
- **Health**: `/api/v1/health`
- **GitHub**: Issues and PRs welcome
- **Email**: support@documentai.app (TODO)

## License

MIT License - see LICENSE file

---

**Built with ❤️ for SwiftUI developers**
