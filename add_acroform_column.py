#!/usr/bin/env python3
"""Quick script to add acroform column to documents table"""

import psycopg2
import sys

DATABASE_URL = "postgresql://postgres.iixekrmukkpdmmqoheed:OyBok9Gt9664d92o@aws-0-us-east-1.pooler.supabase.com:6543/postgres"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    # Add acroform column if it doesn't exist
    cur.execute("""
        ALTER TABLE documents 
        ADD COLUMN IF NOT EXISTS acroform BOOLEAN DEFAULT FALSE NOT NULL;
    """)
    
    conn.commit()
    print("✅ Successfully added acroform column to documents table")
    
    # Verify
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='documents' AND column_name='acroform';")
    result = cur.fetchone()
    if result:
        print(f"✅ Verified: acroform column exists")
    else:
        print("❌ Column not found after adding")
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
