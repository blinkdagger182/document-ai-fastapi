# DocumentAI Backend - Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         SwiftUI Client                          │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTPS/REST API (JSON camelCase)
                         ↓
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend (Cloud Run)                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Routers    │→ │   Services   │→ │    Models    │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└────────┬────────────────────┬────────────────────┬──────────────┘
         │                    │                    │
    ┌────↓────┐         ┌─────↓─────┐       ┌─────↓─────┐
    │ Supabase│         │  Cloud    │       │PostgreSQL │
    │ Storage │         │  Tasks    │       │    (DB)   │
    └─────────┘         └─────┬─────┘       └───────────┘
                              │
                    ┌─────────┴─────────┐
                    ↓                   ↓
           ┌──────────────┐    ┌──────────────┐
           │  OCR Worker  │    │   Composer   │
           │ (Cloud Run)  │    │   Worker     │
           └──────────────┘    └──────────────┘
```

## Component Details

### API Layer (FastAPI)
- Async/await for non-blocking I/O
- Automatic OpenAPI documentation
- Pydantic validation
- CORS configured for iOS/web clients

### Database Schema
- **documents**: File metadata and processing status
- **field_regions**: Detected form fields with coordinates
- **field_values**: User-entered values
- **users**: User accounts (single-user stub)
- **usage_events**: Metering and analytics

### Worker Architecture
- **OCR Worker**: PaddleOCR for text extraction, field classification
- **Composer Worker**: PyMuPDF for PDF generation with overlaid values

### Storage
- Supabase Storage for file uploads
- Pre-signed URLs for secure downloads

## Data Flow

### Upload & OCR Flow
```
SwiftUI → Upload PDF → API stores file → Cloud Task → OCR Worker
                                                          ↓
SwiftUI ← Poll status ← API ← Update DB ← Extract fields
```

### Form Fill & Compose Flow
```
SwiftUI → Submit values → API stores → Cloud Task → Composer Worker
                                                          ↓
SwiftUI ← Download URL ← API ← Update DB ← Generate PDF
```

## Deployment Architecture (GCP)

```
┌─────────────────────────────────────────────────────────────────┐
│                      Cloud Run (Auto-scaling)                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ API Service  │  │ OCR Worker   │  │  Composer    │         │
│  │   (Public)   │  │  (Private)   │  │   (Private)  │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
         │                    │                    │
    ┌────↓────┐         ┌─────↓─────┐       ┌─────↓─────┐
    │Supabase │         │  Cloud    │       │ Supabase  │
    │ Storage │         │  Tasks    │       │ Postgres  │
    └─────────┘         └───────────┘       └───────────┘
```

## Technology Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + Uvicorn |
| Database | PostgreSQL (Supabase) |
| ORM | SQLAlchemy 2.x + Alembic |
| Workers | Cloud Run + Cloud Tasks |
| OCR | PaddleOCR |
| PDF | PyMuPDF |
| Storage | Supabase Storage |
| Deployment | Docker + Cloud Run |

## Cost Estimate (Solo User)

**FREE within GCP/Supabase free tiers:**
- Cloud Run: 2M requests/month free
- Cloud Tasks: 1M tasks/month free
- Supabase: 500MB DB, 1GB storage free
