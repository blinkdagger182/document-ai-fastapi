# DocumentAI Backend - Quick Start Guide

Get up and running in 5 minutes!

## Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Git

## Option 1: Automated Setup (Recommended)

```bash
# Clone repository
git clone <your-repo-url>
cd documentai-backend

# Run quick start script
chmod +x scripts/quickstart.sh
./scripts/quickstart.sh

# Start API server (Terminal 1)
source venv/bin/activate
uvicorn app.main:app --reload --port 8080

# Start worker (Terminal 2)
source venv/bin/activate
celery -A app.workers.celery_app worker -Q ocr,compose --loglevel=info
```

Visit http://localhost:8080/docs to see the API documentation.

## Option 2: Manual Setup

### Step 1: Install Dependencies

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install packages
pip install -r requirements.txt
```

### Step 2: Configure Environment

```bash
# Copy example config
cp .env.example .env

# Edit .env with your settings (optional for local dev)
# The default values work for local development
```

### Step 3: Start Services

```bash
# Start PostgreSQL and Redis
docker-compose up -d postgres redis

# Wait for services to be ready
sleep 5
```

### Step 4: Initialize Database

```bash
# Run migrations
alembic upgrade head

# Create default user
python scripts/init_db.py
```

### Step 5: Start Application

```bash
# Terminal 1: API Server
uvicorn app.main:app --reload --port 8080

# Terminal 2: Celery Worker
celery -A app.workers.celery_app worker -Q ocr,compose --loglevel=info
```

## Verify Installation

### 1. Check Health Endpoint

```bash
curl http://localhost:8080/api/v1/health
# Expected: {"status":"ok"}
```

### 2. View API Documentation

Open http://localhost:8080/docs in your browser.

### 3. Test Upload (Optional)

```bash
# Create a test PDF
echo "%PDF-1.4" > test.pdf

# Upload it
curl -X POST http://localhost:8080/api/v1/documents/init-upload \
  -F "file=@test.pdf" \
  | jq
```

## Using Makefile Commands

```bash
make help         # Show all commands
make install      # Install dependencies
make dev          # Run API server
make worker       # Run Celery worker
make test         # Run tests
make migrate      # Run database migrations
make docker-up    # Start all services with Docker
make docker-down  # Stop all services
```

## Test the Complete Flow

### 1. Upload a Document

```bash
# Save document ID
DOC_ID=$(curl -X POST http://localhost:8080/api/v1/documents/init-upload \
  -F "file=@sample.pdf" \
  | jq -r '.documentId')

echo "Document ID: $DOC_ID"
```

### 2. Start OCR Processing

```bash
curl -X POST http://localhost:8080/api/v1/documents/$DOC_ID/process
```

### 3. Check Status

```bash
# Poll until ready
while true; do
  STATUS=$(curl -s http://localhost:8080/api/v1/documents/$DOC_ID | jq -r '.document.status')
  echo "Status: $STATUS"
  if [ "$STATUS" = "ready" ]; then
    break
  fi
  sleep 2
done
```

### 4. Get Field Components

```bash
curl http://localhost:8080/api/v1/documents/$DOC_ID | jq '.components'
```

### 5. Submit Values

```bash
# Get first field ID
FIELD_ID=$(curl -s http://localhost:8080/api/v1/documents/$DOC_ID | jq -r '.components[0].fieldId')

# Submit value
curl -X POST http://localhost:8080/api/v1/documents/$DOC_ID/values \
  -H "Content-Type: application/json" \
  -d "{
    \"values\": [
      {\"fieldRegionId\": \"$FIELD_ID\", \"value\": \"Test Value\", \"source\": \"manual\"}
    ]
  }"
```

### 6. Compose PDF

```bash
curl -X POST http://localhost:8080/api/v1/documents/$DOC_ID/compose
```

### 7. Download Filled PDF

```bash
# Wait for composition
sleep 10

# Get download URL
curl http://localhost:8080/api/v1/documents/$DOC_ID/download | jq -r '.filledPdfUrl'
```

## Troubleshooting

### Port Already in Use

```bash
# Find process using port 8080
lsof -i :8080

# Kill it
kill -9 <PID>
```

### Database Connection Error

```bash
# Check if PostgreSQL is running
docker-compose ps postgres

# View logs
docker-compose logs postgres

# Restart
docker-compose restart postgres
```

### Redis Connection Error

```bash
# Check if Redis is running
docker-compose ps redis

# Test connection
redis-cli -h localhost ping
# Expected: PONG
```

### Worker Not Processing Jobs

```bash
# Check worker logs
# Look for connection errors or task failures

# Restart worker
# Ctrl+C and restart: celery -A app.workers.celery_app worker -Q ocr,compose --loglevel=info
```

### OCR Not Working

```bash
# Test OCR locally
python scripts/test_ocr.py sample.pdf

# If PaddleOCR fails to install:
pip install paddlepaddle==2.6.0 --no-deps
pip install paddleocr==2.7.0.3
```

### Import Errors

```bash
# Make sure you're in the virtual environment
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

## Development Tips

### Hot Reload

The API server automatically reloads when you change code (thanks to `--reload` flag).

### View Logs

```bash
# API logs: visible in Terminal 1
# Worker logs: visible in Terminal 2
# Database logs: docker-compose logs postgres
# Redis logs: docker-compose logs redis
```

### Database GUI

```bash
# Install pgAdmin or use psql
psql postgresql://documentai:documentai@localhost:5432/documentai

# List tables
\dt

# Query documents
SELECT id, file_name, status FROM documents;
```

### Redis GUI

```bash
# Use redis-cli
redis-cli -h localhost

# List keys
KEYS *

# Get queue length
LLEN celery
```

### Reset Everything

```bash
# Stop all services
docker-compose down -v

# Remove database
rm -rf postgres_data/

# Start fresh
./scripts/quickstart.sh
```

## Next Steps

1. **Read the API Documentation**: http://localhost:8080/docs
2. **Integrate with SwiftUI**: See [SWIFTUI_INTEGRATION.md](SWIFTUI_INTEGRATION.md)
3. **Deploy to GCP**: See [DEPLOYMENT.md](DEPLOYMENT.md)
4. **Customize OCR**: Edit `app/services/ocr_dispatcher.py`
5. **Add Authentication**: Implement JWT in `app/routers/documents.py`

## Common Use Cases

### Test with Real PDF

```bash
# Download a sample form
curl -o sample.pdf https://www.irs.gov/pub/irs-pdf/fw4.pdf

# Upload and process
curl -X POST http://localhost:8080/api/v1/documents/init-upload \
  -F "file=@sample.pdf" | jq
```

### Monitor Worker Queue

```bash
# Check active tasks
celery -A app.workers.celery_app inspect active

# Check registered tasks
celery -A app.workers.celery_app inspect registered

# Purge queue (careful!)
celery -A app.workers.celery_app purge
```

### Run Tests

```bash
# All tests
pytest

# Specific test
pytest tests/test_api.py::test_health_check

# With coverage
pytest --cov=app tests/
```

## Getting Help

- **API Issues**: Check http://localhost:8080/docs
- **Database Issues**: Check `docker-compose logs postgres`
- **Worker Issues**: Check worker terminal output
- **General Issues**: See [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)

## Production Deployment

Once you're ready to deploy:

1. Update `.env` with production values
2. Set up GCP project: See [DEPLOYMENT.md](DEPLOYMENT.md)
3. Deploy with Terraform or manual scripts
4. Configure monitoring and alerts
5. Set up CI/CD with Cloud Build

---

**Happy coding! 🚀**
