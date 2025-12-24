from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os

# Create database in the trend-catcher directory
DB_PATH = os.path.join(os.path.dirname(__file__), 'trend_catcher.db')
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class TrackedVideo(Base):
    """
    Represents a unique video being tracked for trends.
    """
    __tablename__ = "tracked_videos"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(String, unique=True, index=True)
    author_id = Column(String)
    
    # Metadata
    description = Column(String, nullable=True)
    permalink = Column(String, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime)  # Video upload time
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    
    # Status
    # status can be: 'new', 'monitoring', 'trending', 'stale'
    status = Column(String, default='new')
    
    # Relationships
    stats = relationship("VideoStats", back_populates="video", cascade="all, delete-orphan")

class VideoStats(Base):
    """
    TimeSeries snapshot of video statistics.
    """
    __tablename__ = "video_stats"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("tracked_videos.id"))
    
    collected_at = Column(DateTime, default=datetime.utcnow)
    
    # Raw metrics
    play_count = Column(Integer, default=0)
    digg_count = Column(Integer, default=0)  # Likes
    share_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    
    # Derived metrics
    calculated_velocity = Column(Float, default=0.0)  # Views per hour at this snapshot
    acceleration = Column(Float, default=0.0)         # Change in velocity since last snapshot
    link = Column(String, nullable=True)              # Direct link to the post at this snapshot can be redundant but requested
    
    video = relationship("TrackedVideo", back_populates="stats")

def init_db():
    Base.metadata.create_all(bind=engine)
    print(f"Database initialized at {DB_PATH}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
