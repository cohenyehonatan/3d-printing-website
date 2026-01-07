"""
Database connection and session management for FastAPI
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from pathlib import Path
import os

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./3d_printing.db")

# Create engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize database - create all tables"""
    from .models import Base
    Base.metadata.create_all(bind=engine)
    print("[DATABASE] Tables created successfully")
