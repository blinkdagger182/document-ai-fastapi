#!/usr/bin/env python3
"""
Initialize database with default user and run migrations.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import SessionLocal, engine, Base
from app.models import User
from app.config import settings


def init_db():
    """Initialize database"""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    
    print("Creating default user...")
    db = SessionLocal()
    try:
        # Check if default user exists
        user = db.query(User).filter(User.email == "default@documentai.app").first()
        if not user:
            user = User(email="default@documentai.app")
            db.add(user)
            db.commit()
            print(f"Created default user: {user.email} (ID: {user.id})")
        else:
            print(f"Default user already exists: {user.email} (ID: {user.id})")
    finally:
        db.close()
    
    print("Database initialization complete!")


if __name__ == "__main__":
    init_db()
