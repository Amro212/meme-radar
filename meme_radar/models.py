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


# =============================================================================
# Lowkey Creator Detection Models
# =============================================================================

class Creator(Base):
    """
    TikTok creator profile for lowkey detection.
    
    Stores basic profile info to calculate virality ratios.
    """
    
    __tablename__ = "creators"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    creator_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    follower_count: Mapped[int] = mapped_column(Integer, default=0)
    following_count: Mapped[int] = mapped_column(Integer, default=0)
    video_count: Mapped[int] = mapped_column(Integer, default=0)
    bio: Mapped[Optional[str]] = mapped_column(Text)
    
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    stats: Mapped[list["CreatorStats"]] = relationship(back_populates="creator", cascade="all, delete-orphan")
    hot_videos: Mapped[list["HotVideo"]] = relationship(back_populates="creator", cascade="all, delete-orphan")
    watchlist_entry: Mapped[Optional["Watchlist"]] = relationship(back_populates="creator", uselist=False)
    
    __table_args__ = (
        Index("ix_creators_follower_count", "follower_count"),
    )
    
    def __repr__(self) -> str:
        return f"<Creator(username='{self.username}', followers={self.follower_count})>"


class CreatorStats(Base):
    """
    Rolling statistics for a creator.
    
    Updated incrementally based on their recent videos.
    """
    
    __tablename__ = "creator_stats"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("creators.id"), nullable=False)
    
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    videos_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    
    # Rolling averages (last N videos)
    avg_views: Mapped[float] = mapped_column(Float, default=0.0)
    median_views: Mapped[float] = mapped_column(Float, default=0.0)
    avg_engagement_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_likes: Mapped[float] = mapped_column(Float, default=0.0)
    avg_comments: Mapped[float] = mapped_column(Float, default=0.0)
    avg_shares: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Relationships
    creator: Mapped["Creator"] = relationship(back_populates="stats")
    
    __table_args__ = (
        Index("ix_creator_stats_computed_at", "computed_at"),
    )
    
    def __repr__(self) -> str:
        return f"<CreatorStats(creator_id={self.creator_id}, avg_views={self.avg_views:.0f})>"


class HotVideo(Base):
    """
    Videos that qualify as "lowkey but juicy".
    
    Stores the video with its computed metrics at detection time.
    """
    
    __tablename__ = "hot_videos"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), nullable=False)
    creator_id: Mapped[int] = mapped_column(ForeignKey("creators.id"), nullable=False)
    
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Raw metrics at detection time
    views: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    
    # Computed scores
    virality_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    engagement_rate: Mapped[float] = mapped_column(Float, default=0.0)
    comment_intensity: Mapped[float] = mapped_column(Float, default=0.0)
    spike_factor: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Ratio analysis (per user's criteria)
    likes_to_views_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    shares_to_likes_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    is_discourse_signal: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Final meme-seed score
    meme_seed_score: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Direct TikTok link for reference
    tiktok_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    
    # Relationships
    post: Mapped["Post"] = relationship()
    creator: Mapped["Creator"] = relationship(back_populates="hot_videos")
    
    __table_args__ = (
        Index("ix_hot_videos_detected_at", "detected_at"),
        Index("ix_hot_videos_meme_seed_score", "meme_seed_score"),
        UniqueConstraint("post_id", name="uq_hot_video_post"),
    )
    
    def __repr__(self) -> str:
        return f"<HotVideo(post_id={self.post_id}, score={self.meme_seed_score:.2f})>"


class Watchlist(Base):
    """
    Tracked creators showing meme potential.
    
    Creators are added when they first qualify, and tracked for new content.
    """
    
    __tablename__ = "watchlist"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("creators.id"), unique=True, nullable=False)
    
    first_qualified_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_qualified_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, dropped
    
    # Best metrics seen
    max_virality_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    max_spike_factor: Mapped[float] = mapped_column(Float, default=0.0)
    max_meme_seed_score: Mapped[float] = mapped_column(Float, default=0.0)
    
    qualifying_video_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # TikTok profile link for reference
    tiktok_profile_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    best_video_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    
    # Relationships
    creator: Mapped["Creator"] = relationship(back_populates="watchlist_entry")
    
    __table_args__ = (
        Index("ix_watchlist_status", "status"),
        Index("ix_watchlist_last_qualified", "last_qualified_at"),
    )
    
    def __repr__(self) -> str:
        return f"<Watchlist(creator_id={self.creator_id}, status='{self.status}')>"


class CommentPhrase(Base):
    """
    Aggregated repeated comment phrases.
    
    Tracks meme-like comment patterns across videos.
    """
    
    __tablename__ = "comment_phrases"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    phrase: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Aggregated stats
    video_count: Mapped[int] = mapped_column(Integer, default=0)
    total_occurrences: Mapped[int] = mapped_column(Integer, default=0)
    total_likes: Mapped[int] = mapped_column(Integer, default=0)
    avg_likes: Mapped[float] = mapped_column(Float, default=0.0)
    distinct_commenters: Mapped[int] = mapped_column(Integer, default=0)
    
    __table_args__ = (
        Index("ix_comment_phrases_video_count", "video_count"),
        Index("ix_comment_phrases_last_seen", "last_seen_at"),
    )
    
    def __repr__(self) -> str:
        return f"<CommentPhrase(phrase='{self.phrase[:30]}...', videos={self.video_count})>"

