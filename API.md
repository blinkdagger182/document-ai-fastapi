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
{
  "status": "ok"
}
```

---

### Upload Document

Upload a PDF or image file to start the document processing workflow.

```http
POST /api/v1/documents/init-upload
Content-Type: multipart/form-data
```

**Request**
- `file`: PDF or image file (multipart)

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

**Errors**
- `400`: Invalid file type
- `500`: Upload failed

---

### Start OCR Processing

Enqueue OCR job to extract fields from the document.

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

**Errors**
- `404`: Document not found
- `400`: Document already processed or in wrong state

---

### Get Document Details

Retrieve document status, field components, and field map.

```http
GET /api/v1/documents/{document_id}
```

**Response 200 (Processing)**
```json
{
  "document": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "fileName": "form.pdf",
    "mimeType": "application/pdf",
    "status": "processing",
    "pageCount": null,
    "createdAt": "2024-01-15T10:30:00Z",
    "updatedAt": "2024-01-15T10:30:15Z"
  },
  "components": [],
  "fieldMap": {}
}
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
      "pageIndex": 0,
      "defaultValue": null,
      "options": null
    },
    {
      "id": "660e8400-e29b-41d4-a716-446655440002",
      "fieldId": "660e8400-e29b-41d4-a716-446655440002",
      "type": "date",
      "label": "Date of Birth",
      "placeholder": "Enter Date of Birth",
      "pageIndex": 0,
      "defaultValue": null,
      "options": null
    },
    {
      "id": "660e8400-e29b-41d4-a716-446655440003",
      "fieldId": "660e8400-e29b-41d4-a716-446655440003",
      "type": "checkbox",
      "label": "I agree to terms",
      "placeholder": null,
      "pageIndex": 1,
      "defaultValue": null,
      "options": null
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
    },
    "660e8400-e29b-41d4-a716-446655440002": {
      "id": "660e8400-e29b-41d4-a716-446655440002",
      "pageIndex": 0,
      "x": 0.15,
      "y": 0.35,
      "width": 0.3,
      "height": 0.03,
      "fieldType": "date",
      "label": "Date of Birth",
      "confidence": 0.92
    },
    "660e8400-e29b-41d4-a716-446655440003": {
      "id": "660e8400-e29b-41d4-a716-446655440003",
      "pageIndex": 1,
      "x": 0.1,
      "y": 0.8,
      "width": 0.02,
      "height": 0.02,
      "fieldType": "checkbox",
      "label": "I agree to terms",
      "confidence": 0.88
    }
  }
}
```

**Errors**
- `404`: Document not found

---

### Submit Field Values

Submit user-entered values for form fields.

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
    },
    {
      "fieldRegionId": "660e8400-e29b-41d4-a716-446655440002",
      "value": "1990-05-15",
      "source": "manual"
    },
    {
      "fieldRegionId": "660e8400-e29b-41d4-a716-446655440003",
      "value": "true",
      "source": "manual"
    }
  ]
}
```

**Response 200**
```json
{
  "documentId": "550e8400-e29b-41d4-a716-446655440000",
  "status": "filling"
}
```

**Errors**
- `404`: Document not found
- `400`: Invalid field region ID

---

### Compose Filled PDF

Generate a filled PDF with user values burned into the original document.

```http
POST /api/v1/documents/{document_id}/compose
```

**Response 200**
```json
{
  "documentId": "550e8400-e29b-41d4-a716-446655440000",
  "status": "filling"
}
```

After composition completes, document status will change to `"filled"`.

**Errors**
- `404`: Document not found
- `400`: No values submitted yet

---

### Download Filled PDF

Get a pre-signed URL to download the filled PDF.

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

The URL is valid for 1 hour.

**Errors**
- `404`: Document not found
- `400`: Filled PDF not yet available

---

## Data Types

### DocumentStatus

```
"imported"    - Document uploaded, not yet processed
"processing"  - OCR in progress
"ready"       - OCR complete, ready for user input
"filling"     - PDF composition in progress
"filled"      - Filled PDF ready for download
"failed"      - Processing failed (check error_message)
```

### FieldType

```
"text"        - Single-line text input
"multiline"   - Multi-line text area
"checkbox"    - Boolean checkbox
"date"        - Date picker
"number"      - Numeric input
"signature"   - Signature field
"unknown"     - Unclassified field
```

### FieldSource

```
"manual"      - User-entered value
"autofill"    - Auto-filled from profile
"ai"          - AI-suggested value
```

---

## Coordinate System

Field coordinates in `fieldMap` are normalized to [0, 1] range:

- `x`: Horizontal position (0 = left edge, 1 = right edge)
- `y`: Vertical position (0 = top edge, 1 = bottom edge)
- `width`: Field width as fraction of page width
- `height`: Field height as fraction of page height

To convert to PDF points (for rendering):
```
pdf_x = x * page_width
pdf_y = y * page_height
pdf_width = width * page_width
pdf_height = height * page_height
```

---

## Polling Pattern

For long-running operations (OCR, PDF composition), use polling:

```javascript
async function waitForReady(documentId) {
  const maxAttempts = 60;
  const delayMs = 2000;
  
  for (let i = 0; i < maxAttempts; i++) {
    const response = await fetch(`/api/v1/documents/${documentId}`);
    const data = await response.json();
    
    if (data.document.status === 'ready' || data.document.status === 'filled') {
      return data;
    }
    
    if (data.document.status === 'failed') {
      throw new Error('Processing failed');
    }
    
    await new Promise(resolve => setTimeout(resolve, delayMs));
  }
  
  throw new Error('Timeout waiting for document');
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

Common HTTP status codes:
- `200`: Success
- `201`: Created
- `400`: Bad request (invalid input)
- `404`: Resource not found
- `500`: Internal server error

---

## Rate Limits

Currently no rate limits enforced. For production:
- 100 requests/minute per IP
- 10 concurrent uploads per user
- 1GB max file size

---

## Webhooks (Future)

Planned webhook support for async notifications:

```json
{
  "event": "document.ready",
  "documentId": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15T10:31:00Z"
}
```

Events:
- `document.ready` - OCR complete
- `document.filled` - PDF composition complete
- `document.failed` - Processing failed

---

## Examples

### Complete Flow (cURL)

```bash
# 1. Upload
RESPONSE=$(curl -X POST http://localhost:8080/api/v1/documents/init-upload \
  -F "file=@form.pdf")
DOC_ID=$(echo $RESPONSE | jq -r '.documentId')

# 2. Process
curl -X POST http://localhost:8080/api/v1/documents/$DOC_ID/process

# 3. Wait and get details
sleep 10
curl http://localhost:8080/api/v1/documents/$DOC_ID

# 4. Submit values
curl -X POST http://localhost:8080/api/v1/documents/$DOC_ID/values \
  -H "Content-Type: application/json" \
  -d '{
    "values": [
      {"fieldRegionId": "FIELD_ID", "value": "John Doe", "source": "manual"}
    ]
  }'

# 5. Compose PDF
curl -X POST http://localhost:8080/api/v1/documents/$DOC_ID/compose

# 6. Download
sleep 10
curl http://localhost:8080/api/v1/documents/$DOC_ID/download
```

### Python Client

```python
import requests
import time

BASE_URL = "http://localhost:8080/api/v1"

# Upload
with open("form.pdf", "rb") as f:
    response = requests.post(
        f"{BASE_URL}/documents/init-upload",
        files={"file": f}
    )
doc_id = response.json()["documentId"]

# Process
requests.post(f"{BASE_URL}/documents/{doc_id}/process")

# Poll until ready
while True:
    response = requests.get(f"{BASE_URL}/documents/{doc_id}")
    data = response.json()
    if data["document"]["status"] == "ready":
        break
    time.sleep(2)

# Submit values
values = [
    {"fieldRegionId": field["fieldId"], "value": "test", "source": "manual"}
    for field in data["components"]
]
requests.post(
    f"{BASE_URL}/documents/{doc_id}/values",
    json={"values": values}
)

# Compose and download
requests.post(f"{BASE_URL}/documents/{doc_id}/compose")
time.sleep(10)
response = requests.get(f"{BASE_URL}/documents/{doc_id}/download")
print(response.json()["filledPdfUrl"])
```
