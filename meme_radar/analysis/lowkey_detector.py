"""
Lowkey Creator Detection Module.

Detects "lowkey but juicy" TikTok creators: small/mid-size accounts
with viral outlier videos and strong comment culture.

Components:
- CreatorStatsUpdater: Maintains rolling stats per creator
- LowkeySelector: Scores videos against thresholds
- WatchlistManager: Tracks qualifying creators
- CommentCultureAnalyzer: Analyzes repeated comment phrases
- MemeSeedScorer: Computes final meme-seed scores
"""

import logging
import re
from collections import Counter
from datetime import datetime, timedelta
from statistics import mean, median
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import config
from ..models import (
    Comment,
    CommentPhrase,
    Creator,
    CreatorStats,
    HotVideo,
    Platform,
    Post,
    Watchlist,
)

logger = logging.getLogger(__name__)


class LowkeyAnalyzer:
    """
    Main orchestrator for lowkey creator detection.
    
    Runs the full analysis pipeline on each collection cycle.
    """
    
    def __init__(self, session: Session):
        self.session = session
        self.config = config
        
        # Load thresholds from config
        self.min_followers = config.get("lowkey_detection", "min_followers", default=5000)
        self.max_followers = config.get("lowkey_detection", "max_followers", default=300000)
        self.min_views = config.get("lowkey_detection", "min_views", default=200000)
        self.min_virality_ratio = config.get("lowkey_detection", "min_virality_ratio", default=10.0)
        self.min_engagement_rate = config.get("lowkey_detection", "min_engagement_rate", default=0.08)
        self.min_comment_intensity = config.get("lowkey_detection", "min_comment_intensity", default=0.02)
        self.min_spike_factor = config.get("lowkey_detection", "min_spike_factor", default=3.0)
        self.history_video_count = config.get("lowkey_detection", "history_video_count", default=10)
        self.analysis_window_hours = config.get("lowkey_detection", "analysis_window_hours", default=48)
        self.max_videos_per_run = config.get("lowkey_detection", "max_videos_per_run", default=500)
        
        # Score weights
        weights = config.get("lowkey_detection", "score_weights", default={})
        self.w_virality = weights.get("virality_ratio", 0.25)
        self.w_engagement = weights.get("engagement_rate", 0.20)
        self.w_comment_intensity = weights.get("comment_intensity", 0.20)
        self.w_spike_factor = weights.get("spike_factor", 0.20)
        self.w_phrases = weights.get("repeated_phrases", 0.15)
        
        # Sub-components
        self.stats_updater = CreatorStatsUpdater(session, self.history_video_count)
        self.watchlist_manager = WatchlistManager(session, config)
        self.comment_analyzer = CommentCultureAnalyzer(session, config)
    
    def run_full_analysis(self) -> dict:
        """
        Run the complete lowkey detection pipeline.
        
        Returns:
            Dict with analysis results
        """
        logger.info("Starting lowkey creator detection...")
        
        results = {
            'videos_analyzed': 0,
            'hot_videos_found': 0,
            'creators_updated': 0,
            'watchlist_additions': 0,
            'phrases_detected': 0,
        }
        
        # Get TikTok platform ID
        tiktok = self.session.query(Platform).filter_by(name="tiktok").first()
        if not tiktok:
            logger.warning("TikTok platform not found")
            return results
        
        # Step 1: Get recent videos
        cutoff_time = datetime.utcnow() - timedelta(hours=self.analysis_window_hours)
        recent_posts = (
            self.session.query(Post)
            .filter(Post.platform_id == tiktok.id)
            .filter(Post.collected_at >= cutoff_time)
            .order_by(Post.collected_at.desc())
            .limit(self.max_videos_per_run)
            .all()
        )
        
        results['videos_analyzed'] = len(recent_posts)
        logger.info(f"Analyzing {len(recent_posts)} recent TikTok videos")
        
        # Step 2: Process each video
        hot_videos = []
        creators_seen = set()
        
        for post in recent_posts:
            if not post.author:
                continue
            
            # Get or create creator
            creator = self._get_or_create_creator(post.author)
            if creator:
                creators_seen.add(creator.id)
            
            # Check if video qualifies
            hot_video = self._evaluate_video(post, creator)
            if hot_video:
                hot_videos.append(hot_video)
                
                # Update watchlist
                added = self.watchlist_manager.update_for_video(creator, hot_video)
                if added:
                    results['watchlist_additions'] += 1
        
        results['hot_videos_found'] = len(hot_videos)
        results['creators_updated'] = len(creators_seen)
        
        # Step 3: Update creator stats for seen creators
        for creator_id in creators_seen:
            self.stats_updater.update_creator_stats(creator_id)
        
        # Step 4: Analyze comments for hot videos
        for hot_video in hot_videos:
            phrases = self.comment_analyzer.analyze_video(hot_video.post_id)
            results['phrases_detected'] += len(phrases)
        
        # Step 5: Drop stale watchlist entries
        self.watchlist_manager.cleanup_stale()
        
        self.session.commit()
        
        logger.info(
            f"Lowkey detection complete: {results['hot_videos_found']} hot videos, "
            f"{results['watchlist_additions']} watchlist additions"
        )
        
        return results
    
    def _get_or_create_creator(self, username: str) -> Optional[Creator]:
        """Get or create a creator record."""
        creator = (
            self.session.query(Creator)
            .filter_by(username=username)
            .first()
        )
        
        if not creator:
            # Create new creator (profile will be fetched later)
            creator = Creator(
                creator_id=username,  # Use username as ID for now
                username=username,
                follower_count=0,  # Unknown until fetched
                first_seen_at=datetime.utcnow(),
                last_updated_at=datetime.utcnow(),
            )
            self.session.add(creator)
            self.session.flush()
        
        return creator
    
    def _evaluate_video(self, post: Post, creator: Optional[Creator]) -> Optional[HotVideo]:
        """
        Evaluate if a video qualifies as "lowkey but juicy".
        
        Since TikTok API doesn't reliably return view counts, we use
        likes as the primary metric for viral detection.
        
        Returns HotVideo if it qualifies, None otherwise.
        """
        if not creator:
            return None
        
        # Get raw metrics from post
        # Try multiple keys for views (TikTok API inconsistency)
        views = 0
        if post.raw_metadata:
            views = (
                post.raw_metadata.get('play_count', 0) or
                post.raw_metadata.get('views', 0) or
                post.raw_metadata.get('playCount', 0) or
                0
            )
        
        likes = post.likes or 0
        comments = post.comments_count or 0
        shares = post.shares or 0
        
        # If no views data, estimate from likes (typical TikTok ratio ~15:1)
        if views == 0 and likes > 0:
            views = likes * 15  # Estimated views
        
        # Minimum engagement threshold (use likes if views unavailable)
        min_likes = self.config.get("lowkey_detection", "min_likes", default=100000)
        if likes < min_likes:
            return None
        
        # Skip very large accounts (we want "lowkey" creators)
        # But allow if follower_count is 0 (unknown)
        if creator.follower_count > 0:
            if creator.follower_count > self.max_followers:
                return None
        
        # Calculate metrics
        # Virality: How much this exceeds their follower base
        if creator.follower_count > 0:
            virality_ratio = views / creator.follower_count
        else:
            # Unknown followers - estimate virality from engagement
            virality_ratio = (likes + comments + shares) / 10000  # Arbitrary scale
        
        # Engagement rate (if views available)
        if views > 0:
            engagement_rate = (likes + comments + shares) / views
            comment_intensity = comments / views
        else:
            # Use likes-based ratios
            engagement_rate = comments / max(likes, 1)  # Comment-to-like ratio
            comment_intensity = comments / max(likes, 1)
        
        # Spike factor: How much this beats their own average
        latest_stats = self._get_latest_stats(creator.id)
        if latest_stats and latest_stats.avg_likes > 0:
            spike_factor = likes / latest_stats.avg_likes
        else:
            spike_factor = 1.0  # No baseline
        
        # Check spike threshold (this is the key metric)
        min_spike = self.config.get("lowkey_detection", "min_spike_factor", default=3.0)
        if latest_stats and latest_stats.avg_likes > 0:
            if spike_factor < min_spike:
                return None
        
        # Check if already recorded
        existing = (
            self.session.query(HotVideo)
            .filter_by(post_id=post.id)
            .first()
        )
        if existing:
            return existing
        
        # Calculate meme-seed score
        meme_seed_score = self._calculate_meme_seed_score(
            virality_ratio=virality_ratio,
            engagement_rate=engagement_rate,
            comment_intensity=comment_intensity,
            spike_factor=spike_factor,
            phrase_score=0.0,
        )
        
        # Create hot video record
        hot_video = HotVideo(
            post_id=post.id,
            creator_id=creator.id,
            detected_at=datetime.utcnow(),
            views=views,
            likes=likes,
            comments=comments,
            shares=shares,
            virality_ratio=virality_ratio,
            engagement_rate=engagement_rate,
            comment_intensity=comment_intensity,
            spike_factor=spike_factor,
            meme_seed_score=meme_seed_score,
        )
        
        self.session.add(hot_video)
        self.session.flush()
        
        logger.info(
            f"Hot video detected: @{creator.username} - "
            f"likes={likes:,}, spike={spike_factor:.1f}x, "
            f"score={meme_seed_score:.2f}"
        )
        
        return hot_video
    
    def _get_latest_stats(self, creator_id: int) -> Optional[CreatorStats]:
        """Get the most recent stats for a creator."""
        return (
            self.session.query(CreatorStats)
            .filter_by(creator_id=creator_id)
            .order_by(CreatorStats.computed_at.desc())
            .first()
        )
    
    def _calculate_meme_seed_score(
        self,
        virality_ratio: float,
        engagement_rate: float,
        comment_intensity: float,
        spike_factor: float,
        phrase_score: float,
    ) -> float:
        """
        Calculate composite meme-seed score.
        
        Normalizes each metric and applies weights.
        """
        # Normalize metrics (simple log scaling for large values)
        import math
        
        vr_norm = min(math.log10(virality_ratio + 1) / 2, 1.0)  # Cap at 100x
        er_norm = min(engagement_rate / 0.20, 1.0)  # Cap at 20%
        ci_norm = min(comment_intensity / 0.05, 1.0)  # Cap at 5%
        sf_norm = min(math.log10(spike_factor + 1) / 1.5, 1.0)  # Cap at ~30x
        ph_norm = min(phrase_score, 1.0)
        
        score = (
            vr_norm * self.w_virality +
            er_norm * self.w_engagement +
            ci_norm * self.w_comment_intensity +
            sf_norm * self.w_spike_factor +
            ph_norm * self.w_phrases
        )
        
        return score
    
    def get_top_creators(self, limit: int = 10) -> list[dict]:
        """
        Get top meme-seed creators.
        
        Returns list of creator info with their best metrics.
        """
        results = []
        
        # Get watchlist entries ordered by max score
        watchlist_entries = (
            self.session.query(Watchlist)
            .filter_by(status="active")
            .order_by(Watchlist.max_meme_seed_score.desc())
            .limit(limit)
            .all()
        )
        
        for entry in watchlist_entries:
            creator = entry.creator
            
            # Get their hot videos
            hot_videos = (
                self.session.query(HotVideo)
                .filter_by(creator_id=creator.id)
                .order_by(HotVideo.meme_seed_score.desc())
                .limit(3)
                .all()
            )
            
            results.append({
                'username': creator.username,
                'followers': creator.follower_count,
                'first_qualified': entry.first_qualified_at,
                'last_qualified': entry.last_qualified_at,
                'max_virality_ratio': entry.max_virality_ratio,
                'max_spike_factor': entry.max_spike_factor,
                'max_meme_seed_score': entry.max_meme_seed_score,
                'qualifying_videos': entry.qualifying_video_count,
                'hot_videos': [
                    {
                        'views': v.views,
                        'score': v.meme_seed_score,
                        'post_id': v.post_id,
                    }
                    for v in hot_videos
                ],
            })
        
        return results


class CreatorStatsUpdater:
    """Updates rolling statistics for creators."""
    
    def __init__(self, session: Session, history_count: int = 10):
        self.session = session
        self.history_count = history_count
    
    def update_creator_stats(self, creator_id: int) -> Optional[CreatorStats]:
        """
        Compute and store rolling stats for a creator.
        
        Uses their last N videos in the database.
        """
        creator = self.session.query(Creator).get(creator_id)
        if not creator:
            return None
        
        # Get recent posts by this creator
        posts = (
            self.session.query(Post)
            .filter(Post.author == creator.username)
            .order_by(Post.created_at.desc())
            .limit(self.history_count)
            .all()
        )
        
        if not posts:
            return None
        
        # Calculate stats
        views_list = []
        engagement_rates = []
        likes_list = []
        comments_list = []
        shares_list = []
        
        for post in posts:
            views = post.raw_metadata.get('views', 0) if post.raw_metadata else 0
            likes = post.likes or 0
            comments = post.comments_count or 0
            shares = post.shares or 0
            
            views_list.append(views)
            likes_list.append(likes)
            comments_list.append(comments)
            shares_list.append(shares)
            
            if views > 0:
                engagement_rates.append((likes + comments + shares) / views)
        
        # Create stats record
        stats = CreatorStats(
            creator_id=creator_id,
            computed_at=datetime.utcnow(),
            videos_analyzed=len(posts),
            avg_views=mean(views_list) if views_list else 0,
            median_views=median(views_list) if views_list else 0,
            avg_engagement_rate=mean(engagement_rates) if engagement_rates else 0,
            avg_likes=mean(likes_list) if likes_list else 0,
            avg_comments=mean(comments_list) if comments_list else 0,
            avg_shares=mean(shares_list) if shares_list else 0,
        )
        
        self.session.add(stats)
        return stats


class WatchlistManager:
    """Manages the creator watchlist."""
    
    def __init__(self, session: Session, config):
        self.session = session
        self.drop_days = config.get("lowkey_detection", "watchlist_drop_days", default=30)
    
    def update_for_video(self, creator: Creator, hot_video: HotVideo) -> bool:
        """
        Update watchlist for a qualifying video.
        
        Returns True if creator was newly added.
        """
        existing = (
            self.session.query(Watchlist)
            .filter_by(creator_id=creator.id)
            .first()
        )
        
        if existing:
            # Update existing entry
            existing.last_qualified_at = datetime.utcnow()
            existing.status = "active"
            existing.qualifying_video_count += 1
            existing.max_virality_ratio = max(
                existing.max_virality_ratio, hot_video.virality_ratio
            )
            existing.max_spike_factor = max(
                existing.max_spike_factor, hot_video.spike_factor
            )
            existing.max_meme_seed_score = max(
                existing.max_meme_seed_score, hot_video.meme_seed_score
            )
            return False
        else:
            # Add new entry
            entry = Watchlist(
                creator_id=creator.id,
                first_qualified_at=datetime.utcnow(),
                last_qualified_at=datetime.utcnow(),
                status="active",
                max_virality_ratio=hot_video.virality_ratio,
                max_spike_factor=hot_video.spike_factor,
                max_meme_seed_score=hot_video.meme_seed_score,
                qualifying_video_count=1,
            )
            self.session.add(entry)
            return True
    
    def cleanup_stale(self) -> int:
        """
        Drop creators who haven't qualified recently.
        
        Returns count of dropped entries.
        """
        cutoff = datetime.utcnow() - timedelta(days=self.drop_days)
        
        stale = (
            self.session.query(Watchlist)
            .filter(Watchlist.status == "active")
            .filter(Watchlist.last_qualified_at < cutoff)
            .all()
        )
        
        for entry in stale:
            entry.status = "dropped"
        
        return len(stale)
    
    def get_active_creators(self) -> list[Creator]:
        """Get all active watchlist creators."""
        entries = (
            self.session.query(Watchlist)
            .filter_by(status="active")
            .all()
        )
        return [e.creator for e in entries]


class CommentCultureAnalyzer:
    """Analyzes comment patterns for meme detection."""
    
    def __init__(self, session: Session, config):
        self.session = session
        self.comments_per_video = config.get("lowkey_detection", "comments_per_video", default=50)
    
    def analyze_video(self, post_id: int) -> list[str]:
        """
        Analyze comments on a hot video.
        
        Returns list of detected repeated phrases.
        """
        # Get comments for this post
        comments = (
            self.session.query(Comment)
            .filter_by(post_id=post_id)
            .order_by(Comment.score.desc())
            .limit(self.comments_per_video)
            .all()
        )
        
        if not comments:
            return []
        
        # Normalize and count phrases
        phrase_counts = Counter()
        phrase_likes = {}
        phrase_commenters = {}
        
        for comment in comments:
            normalized = self._normalize_text(comment.text or "")
            if not normalized or len(normalized) < 3:
                continue
            
            phrase_counts[normalized] += 1
            phrase_likes[normalized] = phrase_likes.get(normalized, 0) + (comment.score or 0)
            
            if normalized not in phrase_commenters:
                phrase_commenters[normalized] = set()
            if comment.author:
                phrase_commenters[normalized].add(comment.author)
        
        # Update phrase records for repeated phrases
        detected_phrases = []
        for phrase, count in phrase_counts.items():
            if count >= 2:  # Appears at least twice
                self._update_phrase_record(
                    phrase=phrase,
                    video_increment=1,
                    occurrence_increment=count,
                    likes_increment=phrase_likes.get(phrase, 0),
                    commenter_count=len(phrase_commenters.get(phrase, set())),
                )
                detected_phrases.append(phrase)
        
        return detected_phrases
    
    def _normalize_text(self, text: str) -> str:
        """Normalize comment text for matching."""
        # Lowercase
        text = text.lower()
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        # Keep emojis, remove other punctuation
        text = re.sub(r'[^\w\s\U0001F300-\U0001F9FF]', '', text)
        # Truncate long text
        if len(text) > 200:
            text = text[:200]
        return text
    
    def _update_phrase_record(
        self,
        phrase: str,
        video_increment: int,
        occurrence_increment: int,
        likes_increment: int,
        commenter_count: int,
    ) -> CommentPhrase:
        """Update or create a phrase record."""
        existing = (
            self.session.query(CommentPhrase)
            .filter_by(phrase=phrase)
            .first()
        )
        
        if existing:
            existing.last_seen_at = datetime.utcnow()
            existing.video_count += video_increment
            existing.total_occurrences += occurrence_increment
            existing.total_likes += likes_increment
            existing.distinct_commenters += commenter_count
            existing.avg_likes = existing.total_likes / max(existing.total_occurrences, 1)
            return existing
        else:
            record = CommentPhrase(
                phrase=phrase,
                first_seen_at=datetime.utcnow(),
                last_seen_at=datetime.utcnow(),
                video_count=video_increment,
                total_occurrences=occurrence_increment,
                total_likes=likes_increment,
                avg_likes=likes_increment / max(occurrence_increment, 1),
                distinct_commenters=commenter_count,
            )
            self.session.add(record)
            return record
    
    def get_trending_phrases(self, limit: int = 20) -> list[dict]:
        """Get top trending comment phrases."""
        phrases = (
            self.session.query(CommentPhrase)
            .filter(CommentPhrase.video_count >= 2)
            .order_by(CommentPhrase.video_count.desc())
            .limit(limit)
            .all()
        )
        
        return [
            {
                'phrase': p.phrase,
                'video_count': p.video_count,
                'total_occurrences': p.total_occurrences,
                'avg_likes': p.avg_likes,
                'last_seen': p.last_seen_at,
            }
            for p in phrases
        ]
