"""
Comment-meme detection for Meme Radar.

Detects repeated comment phrases that indicate viral "comment memes"
where people spam the same text across multiple posts.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import config
from ..models import Comment, Post, Platform


@dataclass
class CommentMeme:
    """A detected comment meme pattern."""
    normalized_text: str
    original_samples: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    distinct_posts: int = 0
    total_occurrences: int = 0
    total_engagement: int = 0
    distinct_authors: int = 0
    earliest_seen: Optional[datetime] = None
    example_post_urls: list[str] = field(default_factory=list)
    
    @property
    def cross_platform(self) -> bool:
        return len(self.platforms) > 1
    
    @property
    def virality_score(self) -> float:
        """Score based on spread pattern."""
        platform_bonus = 2.0 if self.cross_platform else 1.0
        return (
            self.distinct_posts * 1.0 +
            self.total_engagement * 0.5 +
            self.distinct_authors * 0.3
        ) * platform_bonus


class CommentMemeDetector:
    """
    Detects comment memes - phrases that are repeated across posts.
    
    A comment meme is characterized by:
    - Same normalized text appearing in comments on many distinct posts
    - Spread across multiple authors (not just one spammer)
    - Often crossing platform boundaries
    """
    
    def __init__(self, session: Session):
        self.session = session
        self.config = config
        
        # Thresholds
        self.time_window_minutes = config.get("analysis", "time_window_minutes", default=30)
        self.min_distinct_posts = 5  # Must appear on at least 5 different posts
        self.min_distinct_authors = 3  # From at least 3 different authors
        self.min_comment_engagement = config.get("noise", "min_comment_engagement", default=1)
    
    def detect(
        self,
        since_hours: float = 2.0,
        platform_id: Optional[int] = None,
    ) -> list[CommentMeme]:
        """
        Detect comment memes within a time window.
        
        Args:
            since_hours: How far back to look
            platform_id: Optional filter to a single platform
            
        Returns:
            List of detected CommentMeme patterns
        """
        since_time = datetime.utcnow() - timedelta(hours=since_hours)
        
        # Query for repeated normalized comment text
        query = (
            self.session.query(
                Comment.normalized_text,
                func.count(func.distinct(Comment.post_id)).label('distinct_posts'),
                func.count(Comment.id).label('total_occurrences'),
                func.sum(Comment.score).label('total_engagement'),
                func.count(func.distinct(Comment.author)).label('distinct_authors'),
                func.min(Comment.collected_at).label('earliest_seen'),
            )
            .filter(Comment.collected_at >= since_time)
            .filter(Comment.normalized_text.isnot(None))
            .filter(Comment.normalized_text != '')
            .filter(func.length(Comment.normalized_text) >= 10)  # Ignore very short phrases
        )
        
        if platform_id is not None:
            query = query.join(Post, Comment.post_id == Post.id).filter(
                Post.platform_id == platform_id
            )
        
        results = (
            query
            .group_by(Comment.normalized_text)
            .having(func.count(func.distinct(Comment.post_id)) >= self.min_distinct_posts)
            .having(func.count(func.distinct(Comment.author)) >= self.min_distinct_authors)
            .order_by(func.count(func.distinct(Comment.post_id)).desc())
            .limit(100)  # Top 100 candidates
            .all()
        )
        
        memes = []
        for row in results:
            meme = self._build_comment_meme(row, since_time)
            if meme:
                memes.append(meme)
        
        # Sort by virality score
        memes.sort(key=lambda x: x.virality_score, reverse=True)
        
        return memes
    
    def _build_comment_meme(self, row, since_time: datetime) -> Optional[CommentMeme]:
        """Build a CommentMeme from query results with additional details."""
        normalized_text = row.normalized_text
        
        # Get original text samples and platform distribution
        samples = (
            self.session.query(Comment.text, Post.platform_id)
            .join(Post, Comment.post_id == Post.id)
            .filter(Comment.normalized_text == normalized_text)
            .filter(Comment.collected_at >= since_time)
            .limit(10)
            .all()
        )
        
        if not samples:
            return None
        
        original_texts = list(set(s[0] for s in samples if s[0]))[:5]
        platform_ids = list(set(s[1] for s in samples))
        
        # Get platform names
        platforms = (
            self.session.query(Platform.name)
            .filter(Platform.id.in_(platform_ids))
            .all()
        )
        platform_names = [p[0] for p in platforms]
        
        # Get example post URLs
        post_urls = (
            self.session.query(Post.permalink)
            .join(Comment, Comment.post_id == Post.id)
            .filter(Comment.normalized_text == normalized_text)
            .filter(Post.permalink.isnot(None))
            .distinct()
            .limit(5)
            .all()
        )
        
        return CommentMeme(
            normalized_text=normalized_text,
            original_samples=original_texts,
            platforms=platform_names,
            distinct_posts=row.distinct_posts,
            total_occurrences=row.total_occurrences,
            total_engagement=row.total_engagement or 0,
            distinct_authors=row.distinct_authors,
            earliest_seen=row.earliest_seen,
            example_post_urls=[p[0] for p in post_urls],
        )
    
    def detect_cross_platform(self, since_hours: float = 2.0) -> list[CommentMeme]:
        """
        Detect comment memes that appear on multiple platforms.
        
        These are particularly strong signals of viral spread.
        """
        all_memes = self.detect(since_hours=since_hours)
        return [m for m in all_memes if m.cross_platform]
