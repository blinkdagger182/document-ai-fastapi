# 🚀 Supabase Quick Start (5 Minutes)

Connect your DocumentAI backend to Supabase in 5 minutes!

## Step 1: Get Your Supabase Password

1. Go to: https://supabase.com/dashboard/project/iixekrmukkpdmmqoheed/settings/database
2. Scroll to **Connection String** section
3. Click **Reset Database Password** if you don't have it
4. Copy the password

## Step 2: Update .env File

Open `.env` and replace `[YOUR-PASSWORD]` with your actual password:

```bash
DATABASE_URL=postgresql://postgres.iixekrmukkpdmmqoheed:YOUR_ACTUAL_PASSWORD@aws-0-us-east-1.pooler.supabase.com:6543/postgres
```

## Step 3: Run Migrations

```bash
# Install dependencies (if not done)
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Create default user
python scripts/init_db.py
```

## Step 4: Start the API

```bash
# Start API server
uvicorn app.main:app --reload --port 8080
```

## Step 5: Test It

```bash
# Health check
curl http://localhost:8080/api/v1/health

# View API docs
open http://localhost:8080/docs
```

## ✅ Done!

Your backend is now connected to Supabase!

## Optional: Setup Supabase Storage

### Create Storage Bucket

1. Go to: https://supabase.com/dashboard/project/iixekrmukkpdmmqoheed/storage/buckets
2. Click **New bucket**
3. Name: `documentai-storage`
4. Make it **Private**
5. Click **Create bucket**

### Update .env for Storage

Add these lines to `.env`:

```bash
# Use Supabase Storage
STORAGE_BACKEND=supabase
SUPABASE_URL=https://iixekrmukkpdmmqoheed.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
SUPABASE_BUCKET_NAME=documentai-storage
```

Get your service role key from:
https://supabase.com/dashboard/project/iixekrmukkpdmmqoheed/settings/api

## Optional: Use Upstash Redis (Free)

Since Supabase doesn't provide Redis, use Upstash:

1. Go to: https://upstash.com/
2. Sign up (free)
3. Create a Redis database
4. Copy the connection string
5. Update `.env`:

```bash
REDIS_URL=rediss://default:YOUR_PASSWORD@YOUR_ENDPOINT.upstash.io:6379
CELERY_BROKER_URL=rediss://default:YOUR_PASSWORD@YOUR_ENDPOINT.upstash.io:6379
CELERY_RESULT_BACKEND=rediss://default:YOUR_PASSWORD@YOUR_ENDPOINT.upstash.io:6379
```

## Cost: $0 for Development! 🎉

- Supabase Free Tier: 500MB database, 1GB storage
- Upstash Free Tier: 10K commands/day
- Modal.com Free Tier: Available for OCR workers

## Need Help?

See full guide: [SUPABASE_SETUP.md](SUPABASE_SETUP.md)

## Your Supabase Dashboard

- **Project**: https://supabase.com/dashboard/project/iixekrmukkpdmmqoheed
- **Database**: https://supabase.com/dashboard/project/iixekrmukkpdmmqoheed/editor
- **Storage**: https://supabase.com/dashboard/project/iixekrmukkpdmmqoheed/storage/buckets
- **API Keys**: https://supabase.com/dashboard/project/iixekrmukkpdmmqoheed/settings/api
