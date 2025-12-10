"""
Database connection and session management for Meme Radar.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import config
from .models import Base, Platform


# Create engine
engine = create_engine(
    config.database_url,
    echo=False,  # Set to True for SQL debugging
    future=True,
)

# Session factory
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    """
    Initialize the database: create all tables and seed platform data.
    """
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Seed platform data
    with get_session() as session:
        _seed_platforms(session)


def _seed_platforms(session: Session) -> None:
    """Seed the platforms table with default platforms."""
    platforms = ["twitter", "tiktok", "instagram", "reddit"]
    
    for name in platforms:
        existing = session.query(Platform).filter_by(name=name).first()
        if not existing:
            session.add(Platform(name=name))
    
    session.commit()


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.
    
    Usage:
        with get_session() as session:
            posts = session.query(Post).all()
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_platform_id(session: Session, platform_name: str) -> int:
    """Get platform ID by name, or raise if not found."""
    platform = session.query(Platform).filter_by(name=platform_name).first()
    if not platform:
        raise ValueError(f"Unknown platform: {platform_name}")
    return platform.id
