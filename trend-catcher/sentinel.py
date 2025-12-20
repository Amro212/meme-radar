import asyncio
import random
import logging
from datetime import datetime, timedelta
from typing import List, Dict

from sqlalchemy.orm import Session
from TikTokApi import TikTokApi

from db import init_db, SessionLocal, TrackedVideo, VideoStats
from utils_auth import init_api
from algorithm import TrendScorer
from notify import Notifier
from creative_center_scraper import get_trending_videos_with_stats

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("trend_catcher.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("sentinel")

class Sentinel:
    """
    The guardian that watches TikTok trends.
    """
    def __init__(self, check_interval: int = 900, headless: bool = True):
        self.check_interval = check_interval
        self.headless = headless
        self.scorer = TrendScorer()
        self.notifier = Notifier()
        self.api = None
        self.db: Session = SessionLocal()
        
        # Anti-detection state
        self.consecutive_errors = 0
        self.last_api_refresh = datetime.min

    async def _get_api(self):
        """Get or refresh API session."""
        now = datetime.utcnow()
        REFRESH_INTERVAL = timedelta(hours=6)
        
        if self.api is None or (now - self.last_api_refresh) > REFRESH_INTERVAL:
            if self.api:
                try:
                    await self.api.close_sessions()
                except:
                    pass
            
            logger.info("Initializing new TikTok API session...")
            self.api = await init_api(headless=self.headless)
            self.last_api_refresh = now
            
        return self.api

    async def run_forever(self):
        """Main monitoring loop."""
        logger.info(f"Sentinel started. Interval: {self.check_interval}s")
        init_db()
        
        while True:
            try:
                await self.check_trends()
                self.consecutive_errors = 0
                
                # Jitter
                jitter = random.uniform(-120, 300) # -2m to +5m
                sleep_time = max(300, self.check_interval + jitter) # Min 5m sleep
                
                logger.info(f"Sleeping for {sleep_time:.1f}s...")
                await asyncio.sleep(sleep_time)
                
            except Exception as e:
                self.consecutive_errors += 1
                logger.error(f"Error in main loop: {e}", exc_info=True)
                
                # Exponential backoff
                backoff = min(3600, 60 * (2 ** self.consecutive_errors))
                logger.warning(f"Backing off for {backoff}s...")
                await asyncio.sleep(backoff)

    async def check_trends(self):
        """Fetch and process trending videos from Creative Center."""
        
        # Use Creative Center scraper to get trending videos with stats
        # This replaces the broken api.trending.videos() and api.hashtag.videos()
        logger.info("Fetching trending videos from Creative Center...")
        
        try:
            videos = await get_trending_videos_with_stats(
                sort_by="Shares",
                count=15,
                headless=self.headless
            )
        except Exception as e:
            logger.error(f"Failed to fetch videos: {e}")
            raise e

        if not videos:
            logger.warning("No videos received from Creative Center.")
            return

        logger.info(f"Received {len(videos)} videos. Processing...")
        
        # Calculate current timestamp once for the batch
        now = datetime.utcnow()
        
        # 1. First pass: extract metrics and calc velocity
        batch_data = []
        for video in videos:
            try:
                v_id = video.video_id
                author = video.author
                
                create_time = datetime.fromtimestamp(video.create_time)
                
                # Filter out videos older than 7 days
                age_seconds = (now - create_time).total_seconds()
                age_hours = age_seconds / 3600
                if age_hours > 168:  # 7 days
                    logger.debug(f"Skipping old video: {v_id} (Age: {age_hours:.1f}h)")
                    continue

                # Stats from VideoMetrics
                stats = {
                    'playCount': video.play_count,
                    'diggCount': video.like_count,
                    'commentCount': video.comment_count,
                    'shareCount': video.share_count
                }
                play_count = video.play_count
                
                velocity = self.scorer.calculate_velocity(play_count, create_time, now)
                
                permalink = video.video_url

                batch_data.append({
                    'video': video,
                    'id': v_id,
                    'author': author,
                    'create_time': create_time,
                    'stats': stats,
                    'velocity': velocity,
                    'desc': video.description[:500] if video.description else "",
                    'permalink': permalink
                })
            except Exception as e:
                logger.debug(f"Skipping malformed video: {e}")
                continue

        # Extract velocities for percentile calculation
        all_velocities = [d['velocity'] for d in batch_data]
        
        # 2. Second pass: DB ops and classification
        new_trends_found = 0
        
        for data in batch_data:
            # Check if exists
            tracked_video = self.db.query(TrackedVideo).filter_by(video_id=data['id']).first()
            
            is_new = False
            acceleration = 0.0
            
            if not tracked_video:
                # NEW VIDEO
                is_new = True
                tracked_video = TrackedVideo(
                    video_id=data['id'],
                    author_id=data['author'],
                    created_at=data['create_time'],
                    first_seen_at=now,
                    description=data['desc'][:500] if data['desc'] else "",
                    permalink=data['permalink'],
                    status='new'
                )
                self.db.add(tracked_video)
                self.db.flush() # get ID
            else:
                # EXISTING VIDEO - Calc acceleration
                last_stat = self.db.query(VideoStats)\
                    .filter_by(video_id=tracked_video.id)\
                    .order_by(VideoStats.collected_at.desc())\
                    .first()
                
                if last_stat:
                    acceleration = self.scorer.calculate_acceleration(
                        last_stat.calculated_velocity, last_stat.collected_at,
                        data['velocity'], now
                    )
            
            # Update TrackedVideo
            tracked_video.last_seen_at = now
            
            # Insert Stats
            new_stat = VideoStats(
                video_id=tracked_video.id,
                collected_at=now,
                play_count=data['stats'].get('playCount', 0),
                digg_count=data['stats'].get('diggCount', 0),
                share_count=data['stats'].get('shareCount', 0),
                comment_count=data['stats'].get('commentCount', 0),
                calculated_velocity=data['velocity'],
                acceleration=acceleration,
                link=data['permalink']
            )
            self.db.add(new_stat)
            
            # Trend Detection logic
            is_trending = False
            
            if is_new:
                # Check if it's a "Hot Entry"
                if self.scorer.is_potential_trend(data['velocity'], all_velocities):
                    is_trending = True
                    tracked_video.status = 'trending'
                    logger.info(f"HOT ENTRY DETECTED: {tracked_video.permalink} (Vel: {data['velocity']:.0f}/hr)")
                    self.notifier.notify_trend(data, data['velocity'], trend_type="HOT ENTRY")
            else:
                # Check for "Rising Star"
                if self.scorer.is_accelerating_trend(acceleration, data['velocity']):
                    if tracked_video.status != 'trending':
                        is_trending = True
                        tracked_video.status = 'trending'
                        logger.info(f"ACCELERATING TREND: {tracked_video.permalink} (Acc: {acceleration:.0f}/hr^2)")
                        self.notifier.notify_trend(data, data['velocity'], acceleration=acceleration, trend_type="RISING TREND")
            
            if is_trending:
                new_trends_found += 1
                
        self.db.commit()
        logger.info(f"Batch complete. {new_trends_found} trends detected.")

def link_info(video_obj, info_dict):
    """Helper to keep data together if needed"""
    return video_obj


if __name__ == "__main__":
    import sys
    
    # Add trend-catcher to path for imports
    sys.path.insert(0, "trend-catcher")
    
    # Run one check cycle
    async def main():
        sentinel = Sentinel(check_interval=900, headless=False)
        try:
            await sentinel.check_trends()
        finally:
            sentinel.db.close()
    
    asyncio.run(main())
