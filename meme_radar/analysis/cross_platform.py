"""
Cross-platform correlation for Meme Radar.

Detects when the same meme (hashtag, phrase, or image) is trending
across multiple platforms simultaneously, which is a strong signal.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import config
from ..models import TermStat, Platform, TrendCandidate


@dataclass
class CrossPlatformTrend:
    """A trend detected across multiple platforms."""
    term: str
    term_type: str  # hashtag, phrase, image_hash
    platforms: dict[str, dict]  # platform_name -> metrics
    total_frequency: int = 0
    total_engagement: float = 0
    avg_acceleration: float = 0
    boosted_score: float = 0
    example_refs: list[str] = field(default_factory=list)
    
    @property
    def platform_count(self) -> int:
        return len(self.platforms)


class CrossPlatformAnalyzer:
    """
    Analyzes trends across platforms to find cross-platform memes.
    
    Cross-platform trends are boosted in ranking because they indicate
    genuine viral spread rather than platform-specific phenomena.
    """
    
    # Score multiplier for multi-platform trends
    CROSS_PLATFORM_BOOST = {
        2: 1.5,   # 2 platforms -> 1.5x boost
        3: 2.5,   # 3 platforms -> 2.5x boost
        4: 4.0,   # All 4 platforms -> 4x boost
    }
    
    def __init__(self, session: Session):
        self.session = session
        self.config = config
        self.time_window_minutes = config.get("analysis", "time_window_minutes", default=30)
    
    def analyze(
        self,
        since_hours: float = 2.0,
        min_platforms: int = 2,
    ) -> list[CrossPlatformTrend]:
        """
        Find terms/hashes that are trending on multiple platforms.
        
        Args:
            since_hours: Time window to analyze
            min_platforms: Minimum number of platforms required
            
        Returns:
            List of CrossPlatformTrend objects
        """
        since_time = datetime.utcnow() - timedelta(hours=since_hours)
        
        # Find terms appearing on multiple platforms
        cross_platform_terms = self._find_cross_platform_terms(since_time, min_platforms)
        
        trends = []
        for term, term_type, platform_ids in cross_platform_terms:
            trend = self._build_cross_platform_trend(term, term_type, platform_ids, since_time)
            if trend:
                trends.append(trend)
        
        # Sort by boosted score
        trends.sort(key=lambda x: x.boosted_score, reverse=True)
        
        return trends
    
    def _find_cross_platform_terms(
        self,
        since_time: datetime,
        min_platforms: int,
    ) -> list[tuple[str, str, list[int]]]:
        """Find terms that appear on multiple platforms."""
        # Query for terms with their platform distribution
        # Use group_concat instead of array_agg for SQLite compatibility
        results = (
            self.session.query(
                TermStat.term,
                TermStat.term_type,
                func.count(func.distinct(TermStat.platform_id)).label('platform_count'),
                func.group_concat(func.distinct(TermStat.platform_id)).label('platform_ids_str'),
            )
            .filter(TermStat.time_bucket >= since_time)
            .group_by(TermStat.term, TermStat.term_type)
            .having(func.count(func.distinct(TermStat.platform_id)) >= min_platforms)
            .order_by(func.count(func.distinct(TermStat.platform_id)).desc())
            .limit(100)
            .all()
        )
        
        # Convert comma-separated string to list of ints
        return [
            (r.term, r.term_type, [int(x) for x in r.platform_ids_str.split(',')] if r.platform_ids_str else [])
            for r in results
        ]
    
    def _build_cross_platform_trend(
        self,
        term: str,
        term_type: str,
        platform_ids: list[int],
        since_time: datetime,
    ) -> Optional[CrossPlatformTrend]:
        """Build a CrossPlatformTrend with per-platform metrics."""
        platforms = {}
        total_frequency = 0
        total_engagement = 0.0
        acceleration_scores = []
        example_refs = []
        
        for platform_id in platform_ids:
            # Get platform name
            platform = self.session.query(Platform).filter_by(id=platform_id).first()
            if not platform:
                continue
            
            # Get stats for this term on this platform
            stats = (
                self.session.query(TermStat)
                .filter(TermStat.term == term)
                .filter(TermStat.term_type == term_type)
                .filter(TermStat.platform_id == platform_id)
                .filter(TermStat.time_bucket >= since_time)
                .order_by(TermStat.time_bucket.desc())
                .first()
            )
            
            if stats:
                frequency = stats.count_posts + stats.count_comments
                engagement = stats.sum_engagement
                
                platforms[platform.name] = {
                    'frequency': frequency,
                    'engagement': engagement,
                    'authors': stats.distinct_authors,
                }
                
                total_frequency += frequency
                total_engagement += engagement
        
        if not platforms:
            return None
        
        # Get trend candidates for acceleration scores
        candidates = (
            self.session.query(TrendCandidate)
            .filter(TrendCandidate.term == term)
            .filter(TrendCandidate.term_type == term_type)
            .filter(TrendCandidate.detected_at >= since_time)
            .all()
        )
        
        for c in candidates:
            acceleration_scores.append(c.acceleration_score)
            if c.example_refs:
                example_refs.extend(c.example_refs[:2])  # Limit per platform
        
        avg_acceleration = sum(acceleration_scores) / len(acceleration_scores) if acceleration_scores else 1.0
        
        # Calculate boosted score
        platform_count = len(platforms)
        boost_multiplier = self.CROSS_PLATFORM_BOOST.get(platform_count, platform_count)
        boosted_score = (total_frequency * total_engagement * avg_acceleration) ** 0.5 * boost_multiplier
        
        return CrossPlatformTrend(
            term=term,
            term_type=term_type,
            platforms=platforms,
            total_frequency=total_frequency,
            total_engagement=total_engagement,
            avg_acceleration=avg_acceleration,
            boosted_score=boosted_score,
            example_refs=example_refs[:10],
        )
    
    def update_trend_candidates_cross_platform(self, since_hours: float = 2.0) -> int:
        """
        Update TrendCandidate records with cross-platform flags.
        
        Returns:
            Number of candidates updated
        """
        cross_platform_trends = self.analyze(since_hours=since_hours, min_platforms=2)
        
        updated_count = 0
        for trend in cross_platform_trends:
            # Update all candidates for this term
            candidates = (
                self.session.query(TrendCandidate)
                .filter(TrendCandidate.term == trend.term)
                .filter(TrendCandidate.term_type == trend.term_type)
                .all()
            )
            
            for candidate in candidates:
                candidate.cross_platform = True
                candidate.platforms_seen = ','.join(trend.platforms.keys())
                # Boost the trend score
                candidate.trend_score *= self.CROSS_PLATFORM_BOOST.get(trend.platform_count, 1.5)
                updated_count += 1
        
        self.session.commit()
        return updated_count
