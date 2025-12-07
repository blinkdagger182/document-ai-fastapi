# DocumentAI API Documentation

Base URL: `https://your-api.run.app/api/v1`

All endpoints return JSON. Dates are in ISO 8601 format. UUIDs are lowercase with hyphens.

## Authentication

Currently using single-user mode. JWT authentication is stubbed and ready for implementation.

## Endpoints

### Health Check

```http
GET /api/v1/health
```

**Response 200**
```json
{"status": "ok"}
```

---

### Upload Document

```http
POST /api/v1/documents/init-upload
Content-Type: multipart/form-data
```

**Request**: `file` - PDF or image file (multipart)

**Response 201**
```json
{
  "documentId": "550e8400-e29b-41d4-a716-446655440000",
  "document": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "fileName": "form.pdf",
    "mimeType": "application/pdf",
    "status": "imported",
    "pageCount": null,
    "createdAt": "2024-01-15T10:30:00Z",
    "updatedAt": "2024-01-15T10:30:00Z"
  }
}
```

---

### Start OCR Processing

```http
POST /api/v1/documents/{document_id}/process
```

**Response 200**
```json
{
  "documentId": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing"
}
```

---

### Get Document Details

```http
GET /api/v1/documents/{document_id}
```

**Response 200 (Ready)**
```json
{
  "document": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "fileName": "form.pdf",
    "mimeType": "application/pdf",
    "status": "ready",
    "pageCount": 2,
    "createdAt": "2024-01-15T10:30:00Z",
    "updatedAt": "2024-01-15T10:31:00Z"
  },
  "components": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "fieldId": "660e8400-e29b-41d4-a716-446655440001",
      "type": "text",
      "label": "Full Name",
      "placeholder": "Enter Full Name",
      "pageIndex": 0
    }
  ],
  "fieldMap": {
    "660e8400-e29b-41d4-a716-446655440001": {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "pageIndex": 0,
      "x": 0.15,
      "y": 0.25,
      "width": 0.4,
      "height": 0.03,
      "fieldType": "text",
      "label": "Full Name",
      "confidence": 0.95
    }
  }
}
```

---

### Submit Field Values

```http
POST /api/v1/documents/{document_id}/values
Content-Type: application/json
```

**Request**
```json
{
  "values": [
    {
      "fieldRegionId": "660e8400-e29b-41d4-a716-446655440001",
      "value": "John Doe",
      "source": "manual"
    }
  ]
}
```

---

### Compose Filled PDF

```http
POST /api/v1/documents/{document_id}/compose
```

---

### Download Filled PDF

```http
GET /api/v1/documents/{document_id}/download
```

**Response 200**
```json
{
  "documentId": "550e8400-e29b-41d4-a716-446655440000",
  "filledPdfUrl": "https://storage.googleapis.com/bucket/filled/550e8400.pdf?signature=..."
}
```

---

## Data Types

### DocumentStatus
`imported` → `processing` → `ready` → `filling` → `filled` (or `failed`)

### FieldType
`text`, `multiline`, `checkbox`, `date`, `number`, `signature`, `unknown`

### Coordinate System
Field coordinates in `fieldMap` are normalized to [0, 1] range:
- `x`: Horizontal position (0 = left, 1 = right)
- `y`: Vertical position (0 = top, 1 = bottom)

---

## Complete Flow Example (cURL)

```bash
# 1. Upload
DOC_ID=$(curl -X POST http://localhost:8080/api/v1/documents/init-upload \
  -F "file=@form.pdf" | jq -r '.documentId')

# 2. Process
curl -X POST http://localhost:8080/api/v1/documents/$DOC_ID/process

# 3. Poll until ready
curl http://localhost:8080/api/v1/documents/$DOC_ID

# 4. Submit values
curl -X POST http://localhost:8080/api/v1/documents/$DOC_ID/values \
  -H "Content-Type: application/json" \
  -d '{"values": [{"fieldRegionId": "FIELD_ID", "value": "John Doe", "source": "manual"}]}'

# 5. Compose & Download
curl -X POST http://localhost:8080/api/v1/documents/$DOC_ID/compose
curl http://localhost:8080/api/v1/documents/$DOC_ID/download
```
