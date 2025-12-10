"""
SQLAlchemy database models for Meme Radar.

Normalized schema supporting all platforms with unified post, comment,
media, and hashtag storage.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


# Many-to-many association table for posts and hashtags
post_hashtags = Table(
    "post_hashtags",
    Base.metadata,
    Column("post_id", Integer, ForeignKey("posts.id"), primary_key=True),
    Column("hashtag_id", Integer, ForeignKey("hashtags.id"), primary_key=True),
)


class Platform(Base):
    """Platform enumeration table (twitter, tiktok, instagram, reddit)."""
    
    __tablename__ = "platforms"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    
    # Relationships
    posts: Mapped[list["Post"]] = relationship(back_populates="platform")
    
    def __repr__(self) -> str:
        return f"<Platform(name='{self.name}')>"


class Post(Base):
    """
    Unified post storage for all platforms.
    
    Represents tweets, TikTok videos, Instagram posts, and Reddit submissions.
    """
    
    __tablename__ = "posts"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("platforms.id"), nullable=False)
    platform_post_id: Mapped[str] = mapped_column(String(255), nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    text: Mapped[Optional[str]] = mapped_column(Text)
    permalink: Mapped[Optional[str]] = mapped_column(String(512))
    
    # Engagement metrics (normalized where possible)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)  # retweets, shares, etc.
    comments_count: Mapped[int] = mapped_column(Integer, default=0)
    engagement_score: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Reddit-specific
    upvote_ratio: Mapped[Optional[float]] = mapped_column(Float)
    subreddit: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Flags
    media_present: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Raw metadata for platform-specific data
    raw_metadata: Mapped[Optional[dict]] = mapped_column(JSON)
    
    # Relationships
    platform: Mapped["Platform"] = relationship(back_populates="posts")
    media: Mapped[list["Media"]] = relationship(back_populates="post", cascade="all, delete-orphan")
    comments: Mapped[list["Comment"]] = relationship(back_populates="post", cascade="all, delete-orphan")
    hashtags: Mapped[list["Hashtag"]] = relationship(secondary=post_hashtags, back_populates="posts")
    
    __table_args__ = (
        UniqueConstraint("platform_id", "platform_post_id", name="uq_platform_post"),
        Index("ix_posts_created_at", "created_at"),
        Index("ix_posts_collected_at", "collected_at"),
        Index("ix_posts_platform_created", "platform_id", "created_at"),
    )
    
    def __repr__(self) -> str:
        return f"<Post(platform_post_id='{self.platform_post_id}', author='{self.author}')>"


class Media(Base):
    """Media attachments (images, videos, GIFs) with perceptual hashes."""
    
    __tablename__ = "media"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), nullable=False)
    media_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    media_type: Mapped[str] = mapped_column(String(50))  # image, video, gif
    
    # Perceptual hash for image similarity detection
    image_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    
    # Relationships
    post: Mapped["Post"] = relationship(back_populates="media")
    
    def __repr__(self) -> str:
        return f"<Media(type='{self.media_type}', hash='{self.image_hash}')>"


class Comment(Base):
    """Comments on posts across all platforms."""
    
    __tablename__ = "comments"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), nullable=False)
    platform_comment_id: Mapped[Optional[str]] = mapped_column(String(255))
    author: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    text: Mapped[Optional[str]] = mapped_column(Text)
    
    # Normalized text for matching (lowercase, stripped punctuation)
    normalized_text: Mapped[Optional[str]] = mapped_column(Text, index=True)
    
    # Engagement
    score: Mapped[int] = mapped_column(Integer, default=0)  # likes, upvotes
    
    # Raw metadata
    raw_metadata: Mapped[Optional[dict]] = mapped_column(JSON)
    
    # Relationships
    post: Mapped["Post"] = relationship(back_populates="comments")
    
    __table_args__ = (
        Index("ix_comments_collected_at", "collected_at"),
    )
    
    def __repr__(self) -> str:
        return f"<Comment(author='{self.author}', score={self.score})>"


class Hashtag(Base):
    """Normalized hashtag storage."""
    
    __tablename__ = "hashtags"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    tag: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    
    # Relationships
    posts: Mapped[list["Post"]] = relationship(secondary=post_hashtags, back_populates="hashtags")
    
    def __repr__(self) -> str:
        return f"<Hashtag(tag='{self.tag}')>"


class TermStat(Base):
    """
    Time-bucketed statistics for trend detection.
    
    Tracks frequency and engagement of terms (hashtags, phrases, image hashes)
    per time window for acceleration calculations.
    """
    
    __tablename__ = "term_stats"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    term: Mapped[str] = mapped_column(String(512), nullable=False)
    term_type: Mapped[str] = mapped_column(String(50), nullable=False)  # hashtag, phrase, image_hash
    platform_id: Mapped[Optional[int]] = mapped_column(ForeignKey("platforms.id"))
    
    # Time bucket (start of window)
    time_bucket: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    
    # Metrics
    count_posts: Mapped[int] = mapped_column(Integer, default=0)
    count_comments: Mapped[int] = mapped_column(Integer, default=0)
    sum_engagement: Mapped[float] = mapped_column(Float, default=0.0)
    distinct_authors: Mapped[int] = mapped_column(Integer, default=0)
    
    __table_args__ = (
        Index("ix_term_stats_term_bucket", "term", "time_bucket"),
        Index("ix_term_stats_bucket", "time_bucket"),
        UniqueConstraint("term", "term_type", "platform_id", "time_bucket", name="uq_term_stat"),
    )
    
    def __repr__(self) -> str:
        return f"<TermStat(term='{self.term}', bucket='{self.time_bucket}')>"


class TrendCandidate(Base):
    """
    Detected trend candidates with metrics.
    
    Stores flagged terms/images that meet trend thresholds.
    """
    
    __tablename__ = "trend_candidates"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    term: Mapped[str] = mapped_column(String(512), nullable=False)
    term_type: Mapped[str] = mapped_column(String(50), nullable=False)  # hashtag, phrase, image_hash
    platform_id: Mapped[Optional[int]] = mapped_column(ForeignKey("platforms.id"))
    
    # Detection metadata
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Trend metrics
    current_frequency: Mapped[int] = mapped_column(Integer, default=0)
    baseline_frequency: Mapped[float] = mapped_column(Float, default=0.0)
    acceleration_score: Mapped[float] = mapped_column(Float, default=0.0)
    z_score: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Cross-platform flag
    cross_platform: Mapped[bool] = mapped_column(Boolean, default=False)
    platforms_seen: Mapped[Optional[str]] = mapped_column(String(255))  # comma-separated
    
    # Composite score for ranking
    trend_score: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Example references (JSON list of post IDs or URLs)
    example_refs: Mapped[Optional[list]] = mapped_column(JSON)
    
    __table_args__ = (
        Index("ix_trend_candidates_detected_at", "detected_at"),
        Index("ix_trend_candidates_score", "trend_score"),
    )
    
    def __repr__(self) -> str:
        return f"<TrendCandidate(term='{self.term}', score={self.trend_score})>"
