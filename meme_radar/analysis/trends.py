"""
Trend detection algorithm for Meme Radar.

Implements frequency and acceleration-based trend detection by
analyzing time-bucketed statistics.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import mean, stdev
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import config
from ..models import Post, Comment, Hashtag, TermStat, TrendCandidate, Platform


@dataclass
class TrendMetrics:
    """Metrics for a potential trend."""
    term: str
    term_type: str  # hashtag, phrase, image_hash
    platform_id: Optional[int]
    current_frequency: int
    baseline_frequency: float
    baseline_std: float
    acceleration_score: float
    z_score: float
    total_engagement: float
    distinct_authors: int
    example_refs: list[str] = field(default_factory=list)


class TrendAnalyzer:
    """
    Trend detection engine.
    
    Analyzes time-bucketed data to detect:
    - Frequency spikes
    - Acceleration patterns
    - Anomalous z-scores
    """
    
    def __init__(self, session: Session):
        self.session = session
        self.config = config
        
        # Load thresholds from config
        self.time_window_minutes = config.get("analysis", "time_window_minutes", default=30)
        self.history_windows = config.get("analysis", "history_windows", default=6)
        self.min_frequency = config.get("analysis", "min_frequency", default=10)
        self.z_score_threshold = config.get("analysis", "z_score_threshold", default=2.0)
        self.acceleration_threshold = config.get("analysis", "acceleration_threshold", default=3.0)
        self.min_engagement = config.get("analysis", "min_engagement", default=5)
    
    def get_current_bucket(self) -> datetime:
        """Get the start of the current time bucket."""
        now = datetime.utcnow()
        minutes = (now.minute // self.time_window_minutes) * self.time_window_minutes
        return now.replace(minute=minutes, second=0, microsecond=0)
    
    def get_bucket_for_time(self, dt: datetime) -> datetime:
        """Get the time bucket for a given datetime."""
        minutes = (dt.minute // self.time_window_minutes) * self.time_window_minutes
        return dt.replace(minute=minutes, second=0, microsecond=0)
    
    def update_term_stats(self) -> None:
        """
        Update TermStat records based on recent posts and comments.
        
        This aggregates data from the current time window into statistics
        for trend detection.
        """
        current_bucket = self.get_current_bucket()
        window_start = current_bucket
        window_end = current_bucket + timedelta(minutes=self.time_window_minutes)
        
        # Update hashtag stats
        self._update_hashtag_stats(current_bucket, window_start, window_end)
        
        # Update phrase stats from POST TEXT (captions, descriptions)
        self._update_post_phrase_stats(current_bucket, window_start, window_end)
        
        # Update phrase stats from comments (normalized text)
        self._update_comment_phrase_stats(current_bucket, window_start, window_end)
        
        self.session.commit()
    
    def _update_hashtag_stats(
        self,
        bucket: datetime,
        window_start: datetime,
        window_end: datetime,
    ) -> None:
        """Update statistics for hashtags."""
        # Query posts with hashtags in the current window
        posts_with_hashtags = (
            self.session.query(
                Hashtag.tag,
                Post.platform_id,
                func.count(Post.id).label('post_count'),
                func.sum(Post.engagement_score).label('engagement'),
                func.count(func.distinct(Post.author)).label('authors'),
            )
            .join(Post.hashtags)
            .filter(Post.collected_at >= window_start)
            .filter(Post.collected_at < window_end)
            .group_by(Hashtag.tag, Post.platform_id)
            .all()
        )
        
        for row in posts_with_hashtags:
            self._upsert_term_stat(
                term=row.tag,
                term_type='hashtag',
                platform_id=row.platform_id,
                bucket=bucket,
                count_posts=row.post_count,
                count_comments=0,
                sum_engagement=row.engagement or 0,
                distinct_authors=row.authors or 0,
            )
    
    def _update_post_phrase_stats(
        self,
        bucket: datetime,
        window_start: datetime,
        window_end: datetime,
    ) -> None:
        """
        Update statistics for phrases in post text (captions, descriptions).
        
        Extracts 2-3 word phrases to catch viral terms like:
        - "hawk tuah"
        - "very demure"
        - "moo deng"
        """
        import re
        from collections import Counter
        
        # Get all posts in window
        posts = (
            self.session.query(Post)
            .filter(Post.collected_at >= window_start)
            .filter(Post.collected_at < window_end)
            .filter(Post.text.isnot(None))
            .all()
        )
        
        # Extract phrases per platform
        platform_phrases = {}  # platform_id -> Counter of phrases
        
        for post in posts:
            if not post.text:
                continue
            
            # Clean text
            text = post.text.lower()
            # Remove URLs
            text = re.sub(r'http\S+|www\S+', '', text)
            # Remove hashtags (already tracked separately)
            text = re.sub(r'#\w+', '', text)
            # Remove mentions
            text = re.sub(r'@\w+', '', text)
            # Remove special chars except spaces
            text = re.sub(r'[^\w\s]', ' ', text)
            
            # Extract 2-3 word phrases
            words = text.split()
            phrases = []
            
            # 2-word phrases
            for i in range(len(words) - 1):
                phrase = f"{words[i]} {words[i+1]}"
                # Filter out common stop phrases
                if len(phrase) > 4 and not self._is_stop_phrase(phrase):
                    phrases.append(phrase)
            
            # 3-word phrases
            for i in range(len(words) - 2):
                phrase = f"{words[i]} {words[i+1]} {words[i+2]}"
                if len(phrase) > 6 and not self._is_stop_phrase(phrase):
                    phrases.append(phrase)
            
            # Count phrases per platform
            if post.platform_id not in platform_phrases:
                platform_phrases[post.platform_id] = Counter()
            
            for phrase in phrases:
                platform_phrases[post.platform_id][phrase] += 1
        
        # Save stats for phrases that appear multiple times
        for platform_id, phrase_counts in platform_phrases.items():
            for phrase, count in phrase_counts.items():
                if count >= 3:  # Must appear in at least 3 posts
                    # Get posts with this phrase for engagement
                    posts_with_phrase = [
                        p for p in posts
                        if p.platform_id == platform_id and p.text and phrase in p.text.lower()
                    ]
                    
                    engagement = sum(p.engagement_score or 0 for p in posts_with_phrase)
                    authors = len(set(p.author for p in posts_with_phrase if p.author))
                    
                    self._upsert_term_stat(
                        term=phrase,
                        term_type='phrase',
                        platform_id=platform_id,
                        bucket=bucket,
                        count_posts=count,
                        count_comments=0,
                        sum_engagement=engagement,
                        distinct_authors=authors,
                    )
    
    def _is_stop_phrase(self, phrase: str) -> bool:
        """Check if phrase is a common stop phrase to ignore."""
        stop_phrases = {
            'in the', 'on the', 'at the', 'to the', 'for the',
            'of the', 'and the', 'is the', 'it is', 'this is',
            'that is', 'i am', 'you are', 'we are', 'they are',
            'i have', 'you have', 'we have', 'check out', 'link in',
            'follow me', 'like and', 'comment below', 'let me',
            'want to', 'going to', 'have to', 'need to',
        }
        return phrase in stop_phrases
    
    
    def _update_comment_phrase_stats(
        self,
        bucket: datetime,
        window_start: datetime,
        window_end: datetime,
    ) -> None:
        """
        Update statistics for repeated comment phrases.
        
        Groups by normalized_text to find frequently repeated comments.
        """
        # Query comments with their normalized text
        repeated_comments = (
            self.session.query(
                Comment.normalized_text,
                Post.platform_id,
                func.count(Comment.id).label('comment_count'),
                func.count(func.distinct(Comment.post_id)).label('distinct_posts'),
                func.sum(Comment.score).label('total_score'),
                func.count(func.distinct(Comment.author)).label('authors'),
            )
            .join(Post, Comment.post_id == Post.id)
            .filter(Comment.collected_at >= window_start)
            .filter(Comment.collected_at < window_end)
            .filter(Comment.normalized_text.isnot(None))
            .filter(Comment.normalized_text != '')
            .group_by(Comment.normalized_text, Post.platform_id)
            .having(func.count(Comment.id) >= 2)  # Only phrases that appear multiple times
            .all()
        )
        
        for row in repeated_comments:
            self._upsert_term_stat(
                term=row.normalized_text[:512],  # Truncate long phrases
                term_type='phrase',
                platform_id=row.platform_id,
                bucket=bucket,
                count_posts=row.distinct_posts or 0,
                count_comments=row.comment_count,
                sum_engagement=row.total_score or 0,
                distinct_authors=row.authors or 0,
            )
    
    def _upsert_term_stat(
        self,
        term: str,
        term_type: str,
        platform_id: int,
        bucket: datetime,
        count_posts: int,
        count_comments: int,
        sum_engagement: float,
        distinct_authors: int,
    ) -> None:
        """Insert or update a TermStat record."""
        existing = (
            self.session.query(TermStat)
            .filter_by(term=term, term_type=term_type, platform_id=platform_id, time_bucket=bucket)
            .first()
        )
        
        if existing:
            existing.count_posts = count_posts
            existing.count_comments = count_comments
            existing.sum_engagement = sum_engagement
            existing.distinct_authors = distinct_authors
        else:
            stat = TermStat(
                term=term,
                term_type=term_type,
                platform_id=platform_id,
                time_bucket=bucket,
                count_posts=count_posts,
                count_comments=count_comments,
                sum_engagement=sum_engagement,
                distinct_authors=distinct_authors,
            )
            self.session.add(stat)
    
    def detect_trends(self, platform_id: Optional[int] = None) -> list[TrendMetrics]:
        """
        Detect trending terms based on frequency and acceleration.
        
        Args:
            platform_id: Optional platform filter. None for all platforms.
            
        Returns:
            List of TrendMetrics for detected trends.
        """
        current_bucket = self.get_current_bucket()
        trends = []
        
        # Get all terms with stats in the current bucket
        query = self.session.query(TermStat).filter(
            TermStat.time_bucket == current_bucket
        )
        if platform_id is not None:
            query = query.filter(TermStat.platform_id == platform_id)
        
        current_stats = query.all()
        
        for stat in current_stats:
            metrics = self._calculate_trend_metrics(stat, current_bucket)
            
            if metrics and self._is_trending(metrics):
                trends.append(metrics)
        
        # Sort by trend score
        trends.sort(key=lambda x: x.acceleration_score * x.z_score, reverse=True)
        
        return trends
    
    def _calculate_trend_metrics(
        self,
        current_stat: TermStat,
        current_bucket: datetime,
    ) -> Optional[TrendMetrics]:
        """Calculate trend metrics for a term."""
        # Get historical stats for this term
        history_start = current_bucket - timedelta(
            minutes=self.time_window_minutes * self.history_windows
        )
        
        historical_stats = (
            self.session.query(TermStat)
            .filter(TermStat.term == current_stat.term)
            .filter(TermStat.term_type == current_stat.term_type)
            .filter(TermStat.platform_id == current_stat.platform_id)
            .filter(TermStat.time_bucket >= history_start)
            .filter(TermStat.time_bucket < current_bucket)
            .all()
        )
        
        # Calculate current frequency
        current_frequency = current_stat.count_posts + current_stat.count_comments
        
        if current_frequency < self.min_frequency:
            return None
        
        # Calculate baseline
        if not historical_stats:
            baseline_frequency = 0.0
            baseline_std = 1.0  # Avoid division by zero
        else:
            frequencies = [s.count_posts + s.count_comments for s in historical_stats]
            baseline_frequency = mean(frequencies) if frequencies else 0.0
            baseline_std = stdev(frequencies) if len(frequencies) > 1 else 1.0
        
        # Calculate acceleration score
        acceleration_score = (current_frequency + 1) / (baseline_frequency + 1)
        
        # Calculate z-score
        if baseline_std > 0:
            z_score = (current_frequency - baseline_frequency) / baseline_std
        else:
            z_score = current_frequency - baseline_frequency
        
        # Get example references
        example_refs = self._get_example_refs(
            current_stat.term,
            current_stat.term_type,
            current_stat.platform_id,
        )
        
        return TrendMetrics(
            term=current_stat.term,
            term_type=current_stat.term_type,
            platform_id=current_stat.platform_id,
            current_frequency=current_frequency,
            baseline_frequency=baseline_frequency,
            baseline_std=baseline_std,
            acceleration_score=acceleration_score,
            z_score=z_score,
            total_engagement=current_stat.sum_engagement,
            distinct_authors=current_stat.distinct_authors,
            example_refs=example_refs,
        )
    
    def _is_trending(self, metrics: TrendMetrics) -> bool:
        """Determine if metrics indicate a trending term."""
        # Get minimum unique users from config (default 2)
        from .config import Config
        config = Config()
        min_unique_users = config.get("noise", "min_unique_users", default=2)
        
        # Must have multiple unique users (not just one account spamming)
        if metrics.distinct_authors < min_unique_users:
            return False
        
        return (
            metrics.current_frequency >= self.min_frequency and
            (metrics.z_score >= self.z_score_threshold or
             metrics.acceleration_score >= self.acceleration_threshold) and
            metrics.total_engagement >= self.min_engagement
        )
    
    def _get_example_refs(
        self,
        term: str,
        term_type: str,
        platform_id: int,
        limit: int = 5,
    ) -> list[str]:
        """Get example post references for a term."""
        refs = []
        
        if term_type == 'hashtag':
            posts = (
                self.session.query(Post)
                .join(Post.hashtags)
                .filter(Hashtag.tag == term)
                .filter(Post.platform_id == platform_id)
                .order_by(Post.engagement_score.desc())
                .limit(limit)
                .all()
            )
            refs = [p.permalink for p in posts if p.permalink]
            
        elif term_type == 'phrase':
            comments = (
                self.session.query(Comment)
                .join(Post, Comment.post_id == Post.id)
                .filter(Comment.normalized_text == term)
                .filter(Post.platform_id == platform_id)
                .order_by(Comment.score.desc())
                .limit(limit)
                .all()
            )
            # Get parent post URLs
            post_ids = [c.post_id for c in comments]
            if post_ids:
                posts = (
                    self.session.query(Post)
                    .filter(Post.id.in_(post_ids))
                    .all()
                )
                refs = [p.permalink for p in posts if p.permalink]
        
        return refs
    
    def save_trend_candidates(self, trends: list[TrendMetrics]) -> list[TrendCandidate]:
        """Save detected trends as TrendCandidate records."""
        candidates = []
        
        for metrics in trends:
            # Calculate composite trend score
            trend_score = (
                metrics.acceleration_score * 0.4 +
                metrics.z_score * 0.3 +
                (metrics.total_engagement / 100) * 0.2 +
                (metrics.distinct_authors / 10) * 0.1
            )
            
            candidate = TrendCandidate(
                term=metrics.term,
                term_type=metrics.term_type,
                platform_id=metrics.platform_id,
                detected_at=datetime.utcnow(),
                current_frequency=metrics.current_frequency,
                baseline_frequency=metrics.baseline_frequency,
                acceleration_score=metrics.acceleration_score,
                z_score=metrics.z_score,
                trend_score=trend_score,
                example_refs=metrics.example_refs,
            )
            
            self.session.add(candidate)
            candidates.append(candidate)
        
        self.session.commit()
        return candidates
