#!/usr/bin/env python3
"""Test Supabase connection"""
from sqlalchemy import create_engine, text

print('🔍 Testing Supabase connection...')
print()

try:
    # Try direct connection (pooler has issues with this format)
    print('Trying direct connection...')
    engine = create_engine(
        'postgresql://postgres:OyBok9Gt9664d92o@db.iixekrmukkpdmmqoheed.supabase.co:5432/postgres',
        pool_pre_ping=True,
        connect_args={'connect_timeout': 10}
    )
    
    with engine.connect() as conn:
        result = conn.execute(text('SELECT version()'))
        version = result.fetchone()[0]
        print('✅ Connection successful!')
        print()
        print('Database version:')
        print(version[:80] + '...')
        print()
        
        # Check if tables exist
        result = conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """))
        tables = [row[0] for row in result.fetchall()]
        
        if tables:
            print(f'📊 Existing tables ({len(tables)}):')
            for table in tables:
                print(f'  - {table}')
        else:
            print('📊 No tables found (need to run migrations)')
        
        print()
        print('🎉 Supabase is ready to use!')
        
except Exception as e:
    print('❌ Connection failed!')
    print(f'Error: {str(e)}')
    print()
    print('Possible issues:')
    print('  1. Password might be incorrect')
    print('  2. Network/firewall blocking connection')
    print('  3. Supabase project might be paused')
