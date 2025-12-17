"""
Scheduler and orchestrator for Meme Radar.

Coordinates collection runs, analysis pipelines, and data persistence.
"""

import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import config
from .database import get_session, get_platform_id, init_db
from .models import Post, Media, Comment, Hashtag
from .collectors.base import CollectionResult, PostEvent, CommentEvent


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('meme_radar.scheduler')


class MemeRadarOrchestrator:
    """
    Main orchestrator for the Meme Radar system.
    
    Coordinates:
    1. Data collection from all platforms
    2. Data persistence to database
    3. Trend analysis
    4. Result storage
    """
    
    def __init__(self):
        self.config = config
        self.collectors = {}
        self._init_collectors()
    
    def _init_collectors(self) -> None:
        """Initialize available collectors."""
        # Import collectors lazily to handle missing dependencies
        try:
            from .collectors.reddit import RedditCollector
            self.collectors['reddit'] = RedditCollector()
        except ImportError:
            logger.warning("Reddit collector not available")
        
        try:
            from .collectors.twitter import TwitterCollector
            self.collectors['twitter'] = TwitterCollector()
        except ImportError:
            logger.warning("Twitter collector not available")
        
        try:
            from .collectors.tiktok import TikTokCollector
            self.collectors['tiktok'] = TikTokCollector()
        except ImportError:
            logger.warning("TikTok collector not available")
        
        try:
            from .collectors.instagram import InstagramCollector
            self.collectors['instagram'] = InstagramCollector()
        except ImportError:
            logger.warning("Instagram collector not available")
    
    def run_collection(self, platforms: Optional[list[str]] = None) -> dict:
        """
        Run collection for specified platforms.
        
        Args:
            platforms: List of platform names, or None for all
            
        Returns:
            Dict of platform -> CollectionResult
        """
        results = {}
        
        target_platforms = platforms or list(self.collectors.keys())
        
        for platform_name in target_platforms:
            collector = self.collectors.get(platform_name)
            
            if not collector:
                logger.warning(f"No collector for {platform_name}")
                continue
            
            if not collector.is_available():
                logger.warning(f"{platform_name} collector not available (missing dependencies or credentials)")
                continue
            
            if not self.config.get(platform_name, "enabled", default=True):
                logger.info(f"{platform_name} is disabled in config")
                continue
            
            logger.info(f"Collecting from {platform_name}...")
            
            try:
                result = collector.collect()
                results[platform_name] = result
                
                logger.info(
                    f"{platform_name}: {len(result.posts)} posts, "
                    f"{len(result.comments)} comments, "
                    f"{len(result.errors)} errors"
                )
                
                # Persist to database
                self._persist_result(result)
                
            except Exception as e:
                logger.error(f"Error collecting from {platform_name}: {e}")
        
        return results
    
    def _persist_result(self, result: CollectionResult) -> None:
        """Persist a collection result to the database."""
        from .collectors.base import PostEvent, CommentEvent
        
        with get_session() as session:
            platform_id = get_platform_id(session, result.platform)
            
            # Map of platform_post_id -> db Post id
            post_id_map = {}
            
            # Persist posts
            for post_event in result.posts:
                db_post = self._persist_post(session, platform_id, post_event)
                if db_post:
                    post_id_map[post_event.platform_post_id] = db_post.id
            
            # Persist comments
            for post_id_str, comment_event in result.comments:
                db_post_id = post_id_map.get(post_id_str)
                if db_post_id:
                    self._persist_comment(session, db_post_id, comment_event)
    
    def _persist_post(self, session, platform_id: int, post_event: PostEvent) -> Optional[Post]:
        """Persist a single post, returning the DB object."""
        # Check if post already exists
        existing = session.query(Post).filter_by(
            platform_id=platform_id,
            platform_post_id=post_event.platform_post_id
        ).first()
        
        if existing:
            # Update engagement metrics
            existing.likes = post_event.likes
            existing.shares = post_event.shares
            existing.comments_count = post_event.comments_count
            existing.engagement_score = post_event.engagement_score
            return existing
        
        # Create new post
        post = Post(
            platform_id=platform_id,
            platform_post_id=post_event.platform_post_id,
            author=post_event.author,
            created_at=post_event.created_at,
            text=post_event.text,
            permalink=post_event.permalink,
            likes=post_event.likes,
            shares=post_event.shares,
            comments_count=post_event.comments_count,
            engagement_score=post_event.engagement_score,
            upvote_ratio=post_event.upvote_ratio,
            subreddit=post_event.subreddit,
            media_present=len(post_event.media_urls) > 0,
            raw_metadata=post_event.raw_metadata,
        )
        
        session.add(post)
        session.flush()  # Get the ID
        
        # Add hashtags
        for tag in post_event.hashtags:
            hashtag = session.query(Hashtag).filter_by(tag=tag.lower()).first()
            if not hashtag:
                hashtag = Hashtag(tag=tag.lower())
                session.add(hashtag)
                session.flush()
            post.hashtags.append(hashtag)
        
        # Add media
        for media_url, media_type in post_event.media_urls:
            media = Media(
                post_id=post.id,
                media_url=media_url,
                media_type=media_type,
            )
            session.add(media)
        
        return post
    
    def _persist_comment(self, session, post_id: int, comment_event: CommentEvent) -> Optional[Comment]:
        """Persist a single comment."""
        # Check if comment already exists
        if comment_event.platform_comment_id:
            existing = session.query(Comment).filter_by(
                post_id=post_id,
                platform_comment_id=comment_event.platform_comment_id
            ).first()
            
            if existing:
                existing.score = comment_event.score
                return existing
        
        comment = Comment(
            post_id=post_id,
            platform_comment_id=comment_event.platform_comment_id,
            author=comment_event.author,
            created_at=comment_event.created_at,
            text=comment_event.text,
            normalized_text=comment_event.normalized_text,
            score=comment_event.score,
            raw_metadata=comment_event.raw_metadata,
        )
        
        session.add(comment)
        return comment
    
    def run_analysis(self) -> dict:
        """
        Run the full analysis pipeline.
        
        Returns:
            Dict with analysis results
        """
        from .analysis.trends import TrendAnalyzer
        from .analysis.comments import CommentMemeDetector
        from .analysis.images import TemplateDetector
        from .analysis.cross_platform import CrossPlatformAnalyzer
        from .analysis.noise import NoiseFilter
        
        results = {
            'trends': [],
            'comment_memes': [],
            'image_templates': [],
            'cross_platform': [],
        }
        
        with get_session() as session:
            # Update term statistics
            logger.info("Updating term statistics...")
            trend_analyzer = TrendAnalyzer(session)
            trend_analyzer.update_term_stats()
            
            # Detect trends
            logger.info("Detecting trends...")
            trends = trend_analyzer.detect_trends()
            
            # Filter noise
            noise_filter = NoiseFilter(session)
            trends = noise_filter.filter_trends(trends)
            
            # Save trend candidates
            candidates = trend_analyzer.save_trend_candidates(trends)
            results['trends'] = [
                {
                    'term': t.term,
                    'type': t.term_type,
                    'frequency': t.current_frequency,
                    'acceleration': t.acceleration_score,
                    'z_score': t.z_score,
                }
                for t in trends[:20]
            ]
            logger.info(f"Detected {len(trends)} trends")
            
            # Detect comment memes
            logger.info("Detecting comment memes...")
            comment_detector = CommentMemeDetector(session)
            comment_memes = comment_detector.detect(since_hours=2.0)
            results['comment_memes'] = [
                {
                    'text': m.normalized_text[:100],
                    'platforms': m.platforms,
                    'occurrences': m.total_occurrences,
                    'posts': m.distinct_posts,
                }
                for m in comment_memes[:10]
            ]
            logger.info(f"Detected {len(comment_memes)} comment memes")
            
            # Detect image templates
            logger.info("Detecting image templates...")
            template_detector = TemplateDetector(session)
            templates = template_detector.detect_templates(since_hours=2.0)
            results['image_templates'] = [
                {
                    'hash': t.image_hash[:16] + '...',
                    'occurrences': t.occurrences,
                    'platforms': t.platforms,
                }
                for t in templates[:10]
            ]
            logger.info(f"Detected {len(templates)} image templates")
            
            # Cross-platform correlation
            logger.info("Analyzing cross-platform trends...")
            cross_analyzer = CrossPlatformAnalyzer(session)
            cross_analyzer.update_trend_candidates_cross_platform()
            results['cross_platform'] = cross_analyzer.analyze(since_hours=2.0)
            logger.info(f"Found {len(results['cross_platform'])} cross-platform trends")
            
            # Lowkey creator detection
            if self.config.get("lowkey_detection", "enabled", default=False):
                logger.info("Running lowkey creator detection...")
                try:
                    from .analysis.lowkey_detector import LowkeyAnalyzer
                    lowkey_analyzer = LowkeyAnalyzer(session)
                    lowkey_results = lowkey_analyzer.run_full_analysis()
                    results['lowkey'] = lowkey_results
                    logger.info(
                        f"Lowkey detection: {lowkey_results.get('hot_videos_found', 0)} hot videos, "
                        f"{lowkey_results.get('watchlist_additions', 0)} watchlist additions"
                    )
                except Exception as e:
                    logger.error(f"Lowkey detection error: {e}")
                    results['lowkey'] = {'error': str(e)}
            
            # Send notifications for high-value trends
            self._notify_trends(session)
        
        return results
    
    def _notify_trends(self, session) -> None:
        """Send Telegram notifications for detected trends and hot videos."""
        try:
            from .telegram_notifier import TelegramNotifier
            from .models import TrendCandidate, HotVideo
            
            notifier = TelegramNotifier(self.config)
            
            if not notifier.is_available():
                return
            
            # Get recent trends (last 30 mins)
            from datetime import timedelta
            cutoff_time = datetime.utcnow() - timedelta(minutes=30)
            
            # Notify on trends (only high acceleration to avoid noise)
            trends = (
                session.query(TrendCandidate)
                .filter(TrendCandidate.detected_at >= cutoff_time)
                .filter(TrendCandidate.acceleration_score >= 2.0)  # Only meaningful acceleration
                .order_by(TrendCandidate.trend_score.desc())
                .limit(5)
                .all()
            )
            
            for trend in trends:
                notifier.notify_trend(
                    term=trend.term,
                    acceleration=trend.acceleration_score,
                    frequency=trend.current_frequency,
                    platform=trend.platform.name if trend.platform else "unknown",
                    zscore=trend.z_score,
                    example_urls=trend.example_refs,
                    unique_users=trend.distinct_authors,
                )
            
            # Notify on hot videos (high score only)
            hot_videos = (
                session.query(HotVideo)
                .filter(HotVideo.detected_at >= cutoff_time)
                .filter(HotVideo.meme_seed_score >= 0.4)  # Threshold for notification
                .order_by(HotVideo.meme_seed_score.desc())
                .limit(5)
                .all()
            )
            
            for video in hot_videos:
                # Get post data for caption and hashtags
                post = video.post
                caption = post.text if post else None
                hashtags = []
                if post and post.hashtags:
                    hashtags = [h.tag for h in post.hashtags[:5]]
                
                notifier.notify_hot_video(
                    username=video.creator.username if video.creator else "unknown",
                    likes=video.likes,
                    shares=video.shares,
                    comments=video.comments,
                    views=video.views,
                    spike_factor=video.spike_factor,
                    meme_score=video.meme_seed_score,
                    video_url=video.tiktok_url,
                    caption=caption,
                    hashtags=hashtags,
                    is_discourse=video.is_discourse_signal,
                    likes_to_views=video.likes_to_views_ratio,
                    shares_to_likes=video.shares_to_likes_ratio,
                )
                
        except Exception as e:
            logger.error(f"Notification error: {e}")
    
    def run_full_cycle(self, platforms: Optional[list[str]] = None) -> dict:
        """
        Run a complete collection + analysis cycle.
        """
        logger.info("Starting full collection cycle...")
        
        # Collection
        collection_results = self.run_collection(platforms)
        
        # Analysis
        analysis_results = self.run_analysis()
        
        logger.info("Collection cycle complete")
        
        return {
            'collection': {
                platform: {
                    'posts': len(r.posts),
                    'comments': len(r.comments),
                    'errors': r.errors,
                }
                for platform, r in collection_results.items()
            },
            'analysis': analysis_results,
        }


class Scheduler:
    """
    Scheduled execution of the Meme Radar.
    """
    
    def __init__(self, orchestrator: Optional[MemeRadarOrchestrator] = None):
        self.orchestrator = orchestrator or MemeRadarOrchestrator()
        self.config = config
        self._scheduler = None
    
    def start(self, blocking: bool = True) -> None:
        """
        Start the scheduler.
        
        Args:
            blocking: If True, block the main thread
        """
        interval_minutes = self.config.scheduler_interval
        
        if blocking:
            self._scheduler = BlockingScheduler()
        else:
            self._scheduler = BackgroundScheduler()
        
        # Schedule the collection job
        self._scheduler.add_job(
            self._run_cycle,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id='meme_radar_cycle',
            name='Meme Radar Collection Cycle',
            replace_existing=True,
        )
        
        logger.info(f"Starting scheduler with {interval_minutes} minute interval")
        
        # Send Telegram startup notification
        try:
            from .telegram_notifier import TelegramNotifier
            notifier = TelegramNotifier(self.config)
            if notifier.is_available():
                notifier.send_startup_message()
        except Exception as e:
            logger.warning(f"Could not send startup notification: {e}")
        
        # Run immediately on start
        self._run_cycle()
        
        self._scheduler.start()
    
    def stop(self) -> None:
        """Stop the scheduler."""
        if self._scheduler:
            self._scheduler.shutdown()
            logger.info("Scheduler stopped")
    
    def _run_cycle(self) -> None:
        """Execute a single collection cycle."""
        logger.info(f"Running scheduled cycle at {datetime.utcnow()}")
        try:
            self.orchestrator.run_full_cycle()
        except Exception as e:
            logger.error(f"Cycle error: {e}")
