#!/bin/bash
# Quick start script for local development

set -e

echo "🚀 DocumentAI Backend - Quick Start"
echo "===================================="

# Check if .env exists
if [ ! -f .env ]; then
    echo "📝 Creating .env file..."
    cp .env.example .env
    echo "⚠️  Please edit .env with your configuration"
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "🐍 Creating virtual environment..."
    python3 -m venv venv
fi

echo "📦 Activating virtual environment..."
source venv/bin/activate

echo "📥 Installing dependencies..."
pip install -r requirements.txt

echo "🐳 Starting Docker services..."
docker-compose up -d postgres redis

echo "⏳ Waiting for services to be ready..."
sleep 5

echo "🗄️  Running database migrations..."
alembic upgrade head

echo "👤 Initializing database with default user..."
python scripts/init_db.py

echo ""
echo "✅ Setup complete!"
echo ""
echo "To start the application:"
echo "  1. Terminal 1: uvicorn app.main:app --reload --port 8080"
echo "  2. Terminal 2: celery -A app.workers.celery_app worker -Q ocr,compose --loglevel=info"
echo ""
echo "API will be available at: http://localhost:8080"
echo "API docs: http://localhost:8080/docs"
echo ""
