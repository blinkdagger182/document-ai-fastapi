# DocumentAI Backend - Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         SwiftUI Client                          │
│  (iOS/iPadOS - MVVM Architecture)                              │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTPS/REST API
                         │ (JSON with camelCase)
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Routers    │  │   Services   │  │    Models    │         │
│  │ (Endpoints)  │→ │  (Business)  │→ │  (Database)  │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└────────┬────────────────────┬────────────────────┬──────────────┘
         │                    │                    │
         │                    │                    │
    ┌────↓────┐         ┌─────↓─────┐       ┌─────↓─────┐
    │ Cloud   │         │   Redis   │       │PostgreSQL │
    │ Storage │         │  (Broker) │       │    (DB)   │
    │ (GCS/S3)│         └─────┬─────┘       └───────────┘
    └─────────┘               │
                              │ Celery Tasks
                              ↓
                    ┌──────────────────┐
                    │  Celery Workers  │
                    │  ┌────────────┐  │
                    │  │ OCR Task   │  │
                    │  │ (PaddleOCR)│  │
                    │  └────────────┘  │
                    │  ┌────────────┐  │
                    │  │ Compose    │  │
                    │  │ (PyMuPDF)  │  │
                    │  └────────────┘  │
                    └──────────────────┘
```

## Component Details

### 1. API Layer (FastAPI)

```
app/main.py
    │
    ├── CORS Middleware
    │   └── Allow iOS/web origins
    │
    ├── Routers
    │   ├── /api/v1/documents/*  (Document operations)
    │   └── /api/v1/health       (Health check)
    │
    └── Dependency Injection
        ├── Database session
        ├── Current user
        └── Storage service
```

**Key Features**:
- Async/await for non-blocking I/O
- Automatic OpenAPI documentation
- Pydantic validation
- Exception handling
- Structured logging

### 2. Database Layer

```
PostgreSQL
    │
    ├── users
    │   └── Single user stub (ready for multi-user)
    │
    ├── documents
    │   ├── id (UUID)
    │   ├── user_id (FK)
    │   ├── file_name
    │   ├── storage_key_original
    │   ├── storage_key_filled
    │   ├── status (enum)
    │   └── timestamps
    │
    ├── field_regions
    │   ├── id (UUID)
    │   ├── document_id (FK)
    │   ├── page_index
    │   ├── x, y, width, height (normalized)
    │   ├── field_type (enum)
    │   ├── label
    │   └── confidence
    │
    ├── field_values
    │   ├── id (UUID)
    │   ├── document_id (FK)
    │   ├── field_region_id (FK)
    │   ├── user_id (FK)
    │   ├── value
    │   └── source (enum)
    │
    └── usage_events
        ├── id (UUID)
        ├── user_id (FK)
        ├── event_type (enum)
        ├── value
        └── created_at
```

**Indexes**:
- `user_id` on all user-related tables
- `document_id` on field_regions and field_values
- `status` on documents
- `hash_fingerprint` on documents (for template reuse)

### 3. Worker Architecture

```
Celery Application
    │
    ├── Broker: Redis
    │   ├── Queue: ocr
    │   └── Queue: compose
    │
    ├── Backend: Redis
    │   └── Task results storage
    │
    └── Tasks
        │
        ├── run_ocr(document_id)
        │   ├── Download file from storage
        │   ├── Convert PDF pages to images
        │   ├── Run PaddleOCR on each page
        │   ├── Extract text boxes + coordinates
        │   ├── Classify field types
        │   ├── Store field_regions
        │   ├── Update document status
        │   └── Log usage events
        │
        └── compose_pdf(document_id)
            ├── Fetch field_regions + field_values
            ├── Download original PDF
            ├── For each field:
            │   ├── Calculate PDF coordinates
            │   ├── Draw text or checkbox
            │   └── Apply to correct page
            ├── Save filled PDF
            ├── Upload to storage
            ├── Update document status
            └── Log usage events
```

### 4. Storage Abstraction

```
StorageService (Protocol)
    │
    ├── GCSStorageService
    │   ├── google-cloud-storage client
    │   ├── upload_file()
    │   ├── download_to_path()
    │   └── generate_presigned_url()
    │
    └── S3StorageService
        ├── boto3 client
        ├── upload_file()
        ├── download_to_path()
        └── generate_presigned_url()
```

**Storage Structure**:
```
bucket/
├── originals/
│   └── {user_id}/
│       └── {hash}/  (original files)
└── filled/
    └── {document_id}.pdf  (filled PDFs)
```

### 5. OCR Dispatcher

```
OCRBackend (Protocol)
    │
    ├── LocalPaddleOCRBackend
    │   ├── PaddleOCR instance
    │   ├── PyMuPDF for PDF→Image
    │   └── Returns OCRResult
    │
    ├── GCPHTTPBackend
    │   ├── HTTP client
    │   ├── POST to GCP endpoint
    │   └── Returns OCRResult
    │
    └── ModalHTTPBackend
        ├── HTTP client
        ├── POST to Modal endpoint
        └── Returns OCRResult
```

**OCR Result Format**:
```python
OCRResult(
    boxes=[
        OCRBox(
            text="Field Label",
            confidence=0.95,
            bbox=[x, y, width, height],  # Normalized [0,1]
            page_index=0
        ),
        ...
    ],
    page_count=2
)
```

## Data Flow Diagrams

### Upload & OCR Flow

```
SwiftUI                 API                  Worker              Storage
   │                     │                     │                    │
   │──Upload PDF────────→│                     │                    │
   │                     │──Store file────────→│                    │
   │                     │←─────────────────────│                    │
   │←─documentId─────────│                     │                    │
   │                     │                     │                    │
   │──Process request───→│                     │                    │
   │                     │──Enqueue OCR task──→│                    │
   │←─status:processing──│                     │                    │
   │                     │                     │                    │
   │                     │                     │──Download file────→│
   │                     │                     │←───────────────────│
   │                     │                     │                    │
   │                     │                     │──Run PaddleOCR     │
   │                     │                     │  (Extract fields)  │
   │                     │                     │                    │
   │                     │                     │──Update DB         │
   │                     │                     │  (field_regions)   │
   │                     │                     │                    │
   │──Poll status───────→│                     │                    │
   │←─status:ready───────│                     │                    │
   │  + components       │                     │                    │
   │  + fieldMap         │                     │                    │
```

### Form Fill & Compose Flow

```
SwiftUI                 API                  Worker              Storage
   │                     │                     │                    │
   │──Submit values─────→│                     │                    │
   │                     │──Store in DB        │                    │
   │←─status:filling─────│                     │                    │
   │                     │                     │                    │
   │──Compose request───→│                     │                    │
   │                     │──Enqueue compose───→│                    │
   │←─status:filling─────│                     │                    │
   │                     │                     │                    │
   │                     │                     │──Download original→│
   │                     │                     │←───────────────────│
   │                     │                     │                    │
   │                     │                     │──Fetch values      │
   │                     │                     │  from DB           │
   │                     │                     │                    │
   │                     │                     │──Compose PDF       │
   │                     │                     │  (PyMuPDF)         │
   │                     │                     │                    │
   │                     │                     │──Upload filled────→│
   │                     │                     │←───────────────────│
   │                     │                     │                    │
   │                     │                     │──Update DB         │
   │                     │                     │  (status:filled)   │
   │                     │                     │                    │
   │──Poll status───────→│                     │                    │
   │←─status:filled──────│                     │                    │
   │                     │                     │                    │
   │──Download request──→│                     │                    │
   │←─presigned URL──────│                     │                    │
   │                     │                     │                    │
   │──Download PDF──────────────────────────────────────────────→│
   │←─PDF file───────────────────────────────────────────────────│
```

## Deployment Architecture

### GCP Production Setup

```
┌─────────────────────────────────────────────────────────────────┐
│                         Internet                                │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ↓
                  ┌──────────────┐
                  │ Cloud Load   │
                  │ Balancer     │
                  └──────┬───────┘
                         │
                         ↓
┌────────────────────────────────────────────────────────────────┐
│                      Cloud Run                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  FastAPI Container (Auto-scaling 0-10 instances)         │ │
│  │  - CPU: 2 vCPU                                           │ │
│  │  - Memory: 2 GB                                          │ │
│  │  - Timeout: 300s                                         │ │
│  └──────────────────────────────────────────────────────────┘ │
└────────┬───────────────────────┬───────────────────┬───────────┘
         │                       │                   │
         ↓                       ↓                   ↓
  ┌─────────────┐        ┌─────────────┐    ┌─────────────┐
  │  Cloud SQL  │        │ Memorystore │    │   Cloud     │
  │ (Postgres)  │        │   (Redis)   │    │  Storage    │
  │             │        │             │    │   (GCS)     │
  │ - 1 vCPU    │        │ - 1 GB      │    │             │
  │ - 3.75 GB   │        │ - Basic     │    │ - Standard  │
  └─────────────┘        └──────┬──────┘    └─────────────┘
                                │
                                │
                         ┌──────↓──────┐
                         │   Compute   │
                         │   Engine    │
                         │  (Workers)  │
                         │             │
                         │ - 3x VMs    │
                         │ - n1-std-2  │
                         │ - Celery    │
                         └─────────────┘
```

### Alternative: Modal.com Workers

```
┌─────────────────────────────────────────────────────────────────┐
│                      Cloud Run (API)                            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ↓
                  ┌──────────────┐
                  │    Redis     │
                  │  (Celery)    │
                  └──────┬───────┘
                         │
                         ↓
                  ┌──────────────┐
                  │  Modal.com   │
                  │  Serverless  │
                  │   Workers    │
                  │              │
                  │ - GPU: T4    │
                  │ - Auto-scale │
                  │ - Pay/use    │
                  └──────────────┘
```

## Security Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Security Layers                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Network Layer                                               │
│     ├── HTTPS only (TLS 1.3)                                   │
│     ├── Cloud Armor (DDoS protection)                          │
│     └── VPC for internal services                              │
│                                                                 │
│  2. Application Layer                                           │
│     ├── CORS (specific origins)                                │
│     ├── JWT authentication (ready)                             │
│     ├── Input validation (Pydantic)                            │
│     └── Rate limiting (TODO)                                   │
│                                                                 │
│  3. Data Layer                                                  │
│     ├── SQL injection protection (ORM)                         │
│     ├── Encrypted connections (SSL)                            │
│     ├── Pre-signed URLs (time-limited)                         │
│     └── Secrets in Secret Manager                              │
│                                                                 │
│  4. Storage Layer                                               │
│     ├── Private buckets (no public access)                     │
│     ├── IAM roles (least privilege)                            │
│     └── Encryption at rest                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Scaling Strategy

### Horizontal Scaling

```
Load: Low (< 10 req/s)
├── Cloud Run: 1-2 instances
├── Workers: 1 VM (2 workers)
└── Cost: ~$100/month

Load: Medium (10-100 req/s)
├── Cloud Run: 2-5 instances
├── Workers: 3 VMs (6 workers)
└── Cost: ~$500/month

Load: High (100-1000 req/s)
├── Cloud Run: 5-20 instances
├── Workers: 10 VMs (20 workers) or Modal.com
├── Redis: Standard tier (5GB)
├── Cloud SQL: High availability
└── Cost: ~$2000/month
```

### Vertical Scaling

```
API (Cloud Run):
├── Small: 1 vCPU, 1 GB RAM
├── Medium: 2 vCPU, 2 GB RAM (default)
└── Large: 4 vCPU, 4 GB RAM

Workers (Compute Engine):
├── Small: e2-medium (2 vCPU, 4 GB)
├── Medium: n1-standard-2 (2 vCPU, 7.5 GB) (default)
└── Large: n1-standard-4 (4 vCPU, 15 GB)

Database (Cloud SQL):
├── Small: db-f1-micro (1 vCPU, 0.6 GB)
├── Medium: db-n1-standard-1 (1 vCPU, 3.75 GB) (default)
└── Large: db-n1-standard-2 (2 vCPU, 7.5 GB)
```

## Monitoring & Observability

```
┌─────────────────────────────────────────────────────────────────┐
│                    Monitoring Stack                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Logs                                                           │
│  ├── Cloud Logging (structured JSON)                           │
│  ├── Log levels: DEBUG, INFO, WARNING, ERROR                   │
│  └── Retention: 30 days                                        │
│                                                                 │
│  Metrics                                                        │
│  ├── Cloud Run: Request count, latency, errors                │
│  ├── Cloud SQL: Connections, queries, CPU                     │
│  ├── Redis: Memory, connections, commands                     │
│  └── Workers: Task count, duration, failures                  │
│                                                                 │
│  Traces (TODO)                                                  │
│  ├── OpenTelemetry                                             │
│  ├── Request tracing                                           │
│  └── Distributed tracing                                       │
│                                                                 │
│  Alerts                                                         │
│  ├── Error rate > 5%                                           │
│  ├── Latency > 5s (p95)                                        │
│  ├── Worker queue > 100                                        │
│  └── Database connections > 80%                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Technology Stack Summary

| Layer | Technology | Purpose |
|-------|-----------|---------|
| API | FastAPI | REST endpoints |
| Server | Uvicorn | ASGI server |
| Database | PostgreSQL | Persistent storage |
| ORM | SQLAlchemy 2.x | Database abstraction |
| Migrations | Alembic | Schema versioning |
| Validation | Pydantic v2 | Request/response models |
| Workers | Celery | Async job processing |
| Broker | Redis | Task queue |
| OCR | PaddleOCR | Text extraction |
| PDF | PyMuPDF | PDF manipulation |
| Storage | GCS/S3 | File storage |
| Deployment | Docker | Containerization |
| IaC | Terraform | Infrastructure |
| CI/CD | Cloud Build | Automation |
| Hosting | Cloud Run | Serverless API |
| Compute | Compute Engine | Worker VMs |

---

**For implementation details, see [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)**
