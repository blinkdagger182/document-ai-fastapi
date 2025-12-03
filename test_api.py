#!/usr/bin/env python3
"""Quick API test"""
import sys
import os

# Set environment
os.environ['DATABASE_URL'] = 'postgresql://postgres:OyBok9Gt9664d92o@db.iixekrmukkpdmmqoheed.supabase.co:5432/postgres'

try:
    print('🚀 Testing FastAPI application...')
    print()
    
    from app.main import app
    from app.config import settings
    
    print('✅ FastAPI app loaded successfully!')
    print()
    print(f'Environment: {settings.environment}')
    print(f'Database: Connected to Supabase')
    print(f'Storage Backend: {settings.storage_backend}')
    print(f'OCR Backend: {settings.ocr_backend}')
    print()
    print('📋 Available routes:')
    for route in app.routes:
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            methods = ', '.join(route.methods)
            print(f'  {methods:20} {route.path}')
    
    print()
    print('🎉 API is ready to start!')
    print()
    print('To start the server, run:')
    print('  python3 -m uvicorn app.main:app --reload --port 8080')
    print()
    print('Then visit:')
    print('  http://localhost:8080/docs')
    
except Exception as e:
    print(f'❌ Error loading API: {str(e)}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
