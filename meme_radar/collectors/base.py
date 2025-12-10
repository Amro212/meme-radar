"""
Base collector class and utilities for platform-specific collectors.

All collectors inherit from BaseCollector and return standardized event data.
"""

import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from ..config import config


@dataclass
class PostEvent:
    """
    Standardized post event returned by all collectors.
    
    Maps directly to the Post model.
    """
    platform: str
    platform_post_id: str
    author: Optional[str] = None
    created_at: Optional[datetime] = None
    text: Optional[str] = None
    permalink: Optional[str] = None
    likes: int = 0
    shares: int = 0
    comments_count: int = 0
    engagement_score: float = 0.0
    hashtags: list[str] = field(default_factory=list)
    media_urls: list[tuple[str, str]] = field(default_factory=list)  # (url, type)
    raw_metadata: Optional[dict] = None
    
    # Reddit-specific
    upvote_ratio: Optional[float] = None
    subreddit: Optional[str] = None


@dataclass
class CommentEvent:
    """
    Standardized comment event returned by collectors.
    
    Maps directly to the Comment model.
    """
    platform_comment_id: Optional[str] = None
    author: Optional[str] = None
    created_at: Optional[datetime] = None
    text: Optional[str] = None
    normalized_text: Optional[str] = None
    score: int = 0
    raw_metadata: Optional[dict] = None


@dataclass
class CollectionResult:
    """Result of a collection run."""
    platform: str
    posts: list[PostEvent] = field(default_factory=list)
    comments: list[tuple[str, CommentEvent]] = field(default_factory=list)  # (post_id, comment)
    errors: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    @property
    def success(self) -> bool:
        return len(self.errors) == 0 or len(self.posts) > 0


class BaseCollector(ABC):
    """
    Abstract base class for platform collectors.
    
    All collectors must implement the collect() method and return
    standardized PostEvent and CommentEvent objects.
    """
    
    PLATFORM_NAME: str = ""
    
    def __init__(self):
        self.config = config
    
    @abstractmethod
    def collect(self) -> CollectionResult:
        """
        Collect posts and comments from the platform.
        
        Returns:
            CollectionResult with posts, comments, and any errors.
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this collector is available (dependencies installed, credentials set)."""
        pass
    
    def extract_hashtags(self, text: str) -> list[str]:
        """Extract hashtags from text and return lowercased list."""
        if not text:
            return []
        hashtags = re.findall(r'#(\w+)', text)
        return [tag.lower() for tag in hashtags]
    
    def normalize_comment_text(self, text: str) -> str:
        """
        Normalize comment text for matching.
        
        - Lowercase
        - Strip punctuation
        - Normalize whitespace
        - Remove trailing emojis (optional, kept as-is for now)
        """
        if not text:
            return ""
        
        # Lowercase
        text = text.lower()
        
        # Remove punctuation except alphanumeric and whitespace
        text = re.sub(r'[^\w\s]', '', text)
        
        # Normalize unicode
        text = unicodedata.normalize('NFKC', text)
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        return text.strip()
    
    def calculate_engagement_score(
        self,
        likes: int = 0,
        shares: int = 0,
        comments: int = 0,
        views: int = 0,
    ) -> float:
        """
        Calculate normalized engagement score.
        
        Weights:
        - Likes: 1x
        - Shares/Retweets: 3x (more valuable signal)
        - Comments: 2x
        - Views: 0.01x (if available)
        """
        return (
            likes * 1.0 +
            shares * 3.0 +
            comments * 2.0 +
            views * 0.01
        )
