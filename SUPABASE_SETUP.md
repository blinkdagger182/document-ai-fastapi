# Supabase Integration Guide

This guide shows how to connect the DocumentAI backend to your Supabase database.

## Supabase Project Details

- **Project Reference**: `iixekrmukkpdmmqoheed`
- **MCP Endpoint**: https://mcp.supabase.com/mcp?project_ref=iixekrmukkpdmmqoheed

## Step 1: Get Supabase Connection String

1. Go to your Supabase Dashboard: https://supabase.com/dashboard/project/iixekrmukkpdmmqoheed
2. Navigate to **Settings** → **Database**
3. Find the **Connection String** section
4. Copy the **Connection pooling** URI (recommended for production)

The format will be:
```
postgresql://postgres.[PROJECT-REF]:[PASSWORD]@aws-0-us-east-1.pooler.supabase.com:6543/postgres
```

Or for direct connection:
```
postgresql://postgres:[PASSWORD]@db.iixekrmukkpdmmqoheed.supabase.co:5432/postgres
```

## Step 2: Update Environment Variables

Update your `.env` file:

```bash
# Supabase Database (Connection Pooling - Recommended)
DATABASE_URL=postgresql://postgres.iixekrmukkpdmmqoheed:[YOUR-PASSWORD]@aws-0-us-east-1.pooler.supabase.com:6543/postgres

# Or Direct Connection
# DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@db.iixekrmukkpdmmqoheed.supabase.co:5432/postgres

# Redis/Celery (keep as is or use Upstash Redis)
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Storage (use Supabase Storage)
STORAGE_BACKEND=s3
S3_BUCKET_NAME=documentai-storage
S3_ENDPOINT_URL=https://iixekrmukkpdmmqoheed.supabase.co/storage/v1/s3
S3_ACCESS_KEY_ID=[YOUR-SUPABASE-ACCESS-KEY]
S3_SECRET_ACCESS_KEY=[YOUR-SUPABASE-SECRET-KEY]

# OCR Backend
OCR_BACKEND=local

# Auth (can integrate with Supabase Auth later)
JWT_SECRET_KEY=dev-secret-key-change-in-production
JWT_ALGORITHM=HS256

# App
ENVIRONMENT=development
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:3000,capacitor://localhost,ionic://localhost
```

## Step 3: Configure Supabase Storage

### Create Storage Bucket

1. Go to **Storage** in Supabase Dashboard
2. Create a new bucket named `documentai-storage`
3. Set it to **Private** (not public)
4. Enable RLS (Row Level Security) if needed

### Get S3 Credentials

Supabase Storage is S3-compatible. To get credentials:

1. Go to **Settings** → **API**
2. Find your **Project URL** and **anon/service_role keys**
3. For S3 access, you'll use:
   - **Endpoint**: `https://iixekrmukkpdmmqoheed.supabase.co/storage/v1/s3`
   - **Access Key**: Your project reference or service role key
   - **Secret Key**: Your service role key

**Note**: Supabase Storage S3 API is in beta. Alternative: Use Supabase Storage REST API directly.

## Step 4: Run Database Migrations

```bash
# Make sure DATABASE_URL is set to Supabase
export DATABASE_URL="postgresql://postgres.iixekrmukkpdmmqoheed:[PASSWORD]@aws-0-us-east-1.pooler.supabase.com:6543/postgres"

# Run migrations
alembic upgrade head

# Initialize default user
python scripts/init_db.py
```

## Step 5: Alternative - Use Supabase Storage REST API

If S3 compatibility doesn't work, create a Supabase-specific storage service:

```python
# app/services/supabase_storage.py
import httpx
from app.config import settings

class SupabaseStorageService:
    def __init__(self):
        self.base_url = f"https://iixekrmukkpdmmqoheed.supabase.co/storage/v1"
        self.bucket = settings.supabase_bucket_name
        self.headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "apikey": settings.supabase_anon_key
        }
    
    async def upload_file(self, *, local_path: str, key: str, content_type: str) -> str:
        with open(local_path, 'rb') as f:
            files = {'file': (key, f, content_type)}
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/object/{self.bucket}/{key}",
                    files=files,
                    headers=self.headers
                )
                response.raise_for_status()
        return f"{self.base_url}/object/public/{self.bucket}/{key}"
    
    async def download_to_path(self, *, key: str, local_path: str) -> None:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/object/{self.bucket}/{key}",
                headers=self.headers
            )
            response.raise_for_status()
            with open(local_path, 'wb') as f:
                f.write(response.content)
    
    def generate_presigned_url(self, *, key: str, expires_in: int = 3600) -> str:
        # Supabase generates signed URLs differently
        return f"{self.base_url}/object/sign/{self.bucket}/{key}?expiresIn={expires_in}"
```

Add to `.env`:
```bash
SUPABASE_URL=https://iixekrmukkpdmmqoheed.supabase.co
SUPABASE_ANON_KEY=[YOUR-ANON-KEY]
SUPABASE_SERVICE_ROLE_KEY=[YOUR-SERVICE-ROLE-KEY]
SUPABASE_BUCKET_NAME=documentai-storage
```

## Step 6: Redis Alternative - Upstash Redis

Since Supabase doesn't provide Redis, use Upstash (serverless Redis):

1. Go to https://upstash.com/
2. Create a free Redis database
3. Get the connection string
4. Update `.env`:

```bash
REDIS_URL=rediss://default:[PASSWORD]@[ENDPOINT].upstash.io:6379
CELERY_BROKER_URL=rediss://default:[PASSWORD]@[ENDPOINT].upstash.io:6379
CELERY_RESULT_BACKEND=rediss://default:[PASSWORD]@[ENDPOINT].upstash.io:6379
```

## Step 7: Test Connection

```bash
# Test database connection
python -c "
from app.database import engine
from sqlalchemy import text
with engine.connect() as conn:
    result = conn.execute(text('SELECT version()'))
    print('Connected to:', result.fetchone()[0])
"

# Start the API
uvicorn app.main:app --reload --port 8080
```

## Supabase-Specific Features

### Use Supabase Auth (Optional)

Instead of JWT stub, integrate Supabase Auth:

```python
# app/services/supabase_auth.py
from supabase import create_client, Client
from app.config import settings

supabase: Client = create_client(
    settings.supabase_url,
    settings.supabase_anon_key
)

def verify_supabase_token(token: str):
    user = supabase.auth.get_user(token)
    return user
```

### Use Supabase Realtime (Optional)

For real-time updates on document status:

```python
# Subscribe to document changes
supabase.table('documents').on('UPDATE', handle_update).subscribe()
```

## Connection Pooling

Supabase provides connection pooling by default. Use the pooler URL for production:

```
postgresql://postgres.iixekrmukkpdmmqoheed:[PASSWORD]@aws-0-us-east-1.pooler.supabase.com:6543/postgres
```

Configure SQLAlchemy pool:

```python
# app/database.py
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,  # Lower for Supabase pooler
    max_overflow=10,
    pool_recycle=3600
)
```

## Deployment with Supabase

### Environment Variables for Production

```bash
# Supabase Database
DATABASE_URL=postgresql://postgres.iixekrmukkpdmmqoheed:[PASSWORD]@aws-0-us-east-1.pooler.supabase.com:6543/postgres

# Upstash Redis
REDIS_URL=rediss://default:[PASSWORD]@[ENDPOINT].upstash.io:6379
CELERY_BROKER_URL=rediss://default:[PASSWORD]@[ENDPOINT].upstash.io:6379
CELERY_RESULT_BACKEND=rediss://default:[PASSWORD]@[ENDPOINT].upstash.io:6379

# Supabase Storage
STORAGE_BACKEND=supabase
SUPABASE_URL=https://iixekrmukkpdmmqoheed.supabase.co
SUPABASE_SERVICE_ROLE_KEY=[YOUR-SERVICE-ROLE-KEY]
SUPABASE_BUCKET_NAME=documentai-storage

# OCR Backend
OCR_BACKEND=modal  # Use Modal.com for serverless workers

# App
ENVIRONMENT=production
LOG_LEVEL=INFO
CORS_ORIGINS=https://your-app.com
```

## Cost Comparison

### Supabase + Upstash + Modal.com (Fully Serverless)

**Free Tier (Development)**:
- Supabase: Free (500MB database, 1GB storage)
- Upstash Redis: Free (10K commands/day)
- Modal.com: Free tier available
- **Total: $0/month** (within free tiers)

**Production (1,000 docs/month)**:
- Supabase Pro: $25/month (8GB database, 100GB storage)
- Upstash Redis: $10/month (pay-as-you-go)
- Modal.com: $50-100/month (GPU workers)
- Cloud Run (API): $30-50/month
- **Total: ~$115-185/month**

**Comparison to GCP-only**:
- GCP (Cloud SQL + Memorystore + VMs): ~$435-460/month
- **Savings: ~$250-345/month** (58-75% cheaper)

## Advantages of Supabase

1. ✅ **Free tier** for development
2. ✅ **Managed PostgreSQL** with automatic backups
3. ✅ **Built-in Auth** (can replace JWT stub)
4. ✅ **Realtime subscriptions** (WebSocket support)
5. ✅ **Storage included** (S3-compatible)
6. ✅ **Auto-scaling** database
7. ✅ **Global CDN** for storage
8. ✅ **Dashboard** for easy management

## Troubleshooting

### Connection Issues

```bash
# Test connection
psql "postgresql://postgres.iixekrmukkpdmmqoheed:[PASSWORD]@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
```

### SSL Required

If you get SSL errors, add `?sslmode=require` to connection string:

```bash
DATABASE_URL=postgresql://postgres.iixekrmukkpdmmqoheed:[PASSWORD]@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require
```

### Pool Size Limits

Supabase free tier has connection limits. Adjust pool size:

```python
pool_size=3,  # Lower for free tier
max_overflow=5
```

## Next Steps

1. Get your Supabase password from the dashboard
2. Update `.env` with Supabase connection string
3. Run migrations: `alembic upgrade head`
4. Test the API: `make dev`
5. Deploy to Cloud Run with Supabase backend

---

**Your Supabase Project**: https://supabase.com/dashboard/project/iixekrmukkpdmmqoheed
