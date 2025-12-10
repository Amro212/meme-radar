"""
Noise filtering for Meme Radar.

Filters out generic phrases, evergreen hashtags, spam,
and other non-meme content to improve signal quality.
"""

import re
from typing import Optional, Set

from sqlalchemy.orm import Session

from ..config import config


class NoiseFilter:
    """
    Filters noise from trend candidates.
    
    Implements several noise reduction strategies:
    - Stop phrases (generic reactions)
    - Evergreen hashtags (always popular, not trends)
    - Spam detection (single account flooding)
    - Promotional content detection
    """
    
    def __init__(self, session: Optional[Session] = None):
        self.session = session
        self.config = config
        
        # Load stop lists from config
        self._stop_phrases: Optional[Set[str]] = None
        self._evergreen_hashtags: Optional[Set[str]] = None
    
    @property
    def stop_phrases(self) -> Set[str]:
        """Lazy-load stop phrases from config."""
        if self._stop_phrases is None:
            phrases = self.config.get("noise", "stop_phrases", default=[])
            self._stop_phrases = set(p.lower().strip() for p in phrases)
        return self._stop_phrases
    
    @property
    def evergreen_hashtags(self) -> Set[str]:
        """Lazy-load evergreen hashtags from config."""
        if self._evergreen_hashtags is None:
            tags = self.config.get("noise", "evergreen_hashtags", default=[])
            self._evergreen_hashtags = set(t.lower().strip() for t in tags)
        return self._evergreen_hashtags
    
    def is_noise(
        self,
        term: str,
        term_type: str,
        engagement: float = 0,
        acceleration: float = 0,
        distinct_authors: int = 0,
    ) -> bool:
        """
        Check if a term should be filtered as noise.
        
        Args:
            term: The term/phrase/hashtag
            term_type: 'hashtag', 'phrase', or 'image_hash'
            engagement: Total engagement score
            acceleration: Acceleration score
            distinct_authors: Number of unique authors
            
        Returns:
            True if the term should be filtered out
        """
        if not term:
            return True
        
        term_lower = term.lower().strip()
        
        # Check term type specific filters
        if term_type == 'hashtag':
            return self._is_noise_hashtag(term_lower, acceleration)
        elif term_type == 'phrase':
            return self._is_noise_phrase(term_lower, distinct_authors)
        
        # Default: not noise
        return False
    
    def _is_noise_hashtag(self, hashtag: str, acceleration: float) -> bool:
        """Check if a hashtag is noise."""
        # Remove # if present
        hashtag = hashtag.lstrip('#')
        
        # Evergreen hashtags are noise unless acceleration is extreme (>10x)
        if hashtag in self.evergreen_hashtags:
            if acceleration < 10.0:
                return True
        
        # Very short hashtags are often noise
        if len(hashtag) < 2:
            return True
        
        # Hashtags that are just numbers
        if hashtag.isdigit():
            return True
        
        return False
    
    def _is_noise_phrase(self, phrase: str, distinct_authors: int) -> bool:
        """Check if a phrase is noise."""
        # Check against stop phrases
        if phrase in self.stop_phrases:
            return True
        
        # Check if it contains a stop phrase
        for stop in self.stop_phrases:
            if stop in phrase:
                # Only filter if the phrase is mostly the stop phrase
                if len(stop) / len(phrase) > 0.7:
                    return True
        
        # Very short phrases are noise
        if len(phrase) < 5:
            return True
        
        # Single word phrases (after normalization) are usually not memes
        if ' ' not in phrase and len(phrase) < 15:
            return True
        
        # Single author = likely spam, not a meme
        if distinct_authors <= 1:
            return True
        
        # Check for promotional patterns
        if self._is_promotional(phrase):
            return True
        
        return False
    
    def _is_promotional(self, text: str) -> bool:
        """Check if text appears to be promotional content."""
        promotional_patterns = [
            r'\b(discount|coupon|promo|sale|off|deal)\b',
            r'\b(link in bio|check out|subscribe|follow)\b',
            r'\b(buy now|shop now|order now|limited time)\b',
            r'\b(http|www\.)\b',
            r'\b\d+%\s*off\b',
            r'\b(giveaway|contest|win)\b',
        ]
        
        for pattern in promotional_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False
    
    def filter_trends(self, trends: list, term_key: str = 'term') -> list:
        """
        Filter a list of trend objects.
        
        Args:
            trends: List of trend objects (dicts or dataclasses)
            term_key: Key/attribute name for the term
            
        Returns:
            Filtered list with noise removed
        """
        filtered = []
        
        for trend in trends:
            # Handle both dict and dataclass
            if hasattr(trend, term_key):
                term = getattr(trend, term_key)
                term_type = getattr(trend, 'term_type', 'phrase')
                engagement = getattr(trend, 'total_engagement', 0)
                acceleration = getattr(trend, 'acceleration_score', 0)
                authors = getattr(trend, 'distinct_authors', 0)
            elif isinstance(trend, dict):
                term = trend.get(term_key, '')
                term_type = trend.get('term_type', 'phrase')
                engagement = trend.get('total_engagement', 0)
                acceleration = trend.get('acceleration_score', 0)
                authors = trend.get('distinct_authors', 0)
            else:
                filtered.append(trend)
                continue
            
            if not self.is_noise(term, term_type, engagement, acceleration, authors):
                filtered.append(trend)
        
        return filtered
    
    def add_stop_phrase(self, phrase: str) -> None:
        """Dynamically add a stop phrase."""
        self.stop_phrases.add(phrase.lower().strip())
    
    def add_evergreen_hashtag(self, hashtag: str) -> None:
        """Dynamically add an evergreen hashtag."""
        self.evergreen_hashtags.add(hashtag.lower().strip().lstrip('#'))
