import asyncio
import random
import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Set

from sqlalchemy.orm import Session
from TikTokApi import TikTokApi

from db import init_db, SessionLocal, TrackedVideo, VideoStats
from utils_auth import init_api
from algorithm import TrendScorer
from notify import Notifier
from creative_center_scraper import get_trending_videos_with_stats
from hashtag_whitelist import WHITELISTED_HASHTAGS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("sentinel.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("sentinel")


def extract_hashtags(text: str) -> Set[str]:
    """Extract hashtags from text and return as lowercase set."""
    if not text:
        return set()
    # Find all hashtags (# followed by alphanumeric characters)
    hashtags = re.findall(r'#(\w+)', text.lower())
    return set(hashtags)


def check_whitelisted_hashtags(text: str) -> List[str]:
    """Check if text contains any whitelisted hashtags."""
    extracted = extract_hashtags(text)
    matched = extracted.intersection(WHITELISTED_HASHTAGS)
    return list(matched)

class Sentinel:
    """
    The guardian that watches TikTok trends.
    Monitors trending videos and notifies when acceleration spikes occur.
    """
    
    def __init__(self, check_interval: int = 900, headless: bool = True):
        """
        Args:
            check_interval: Seconds between checks (default 15 min)
            headless: Run browser in headless mode
        """
        self.check_interval = check_interval
        self.headless = headless
        self.db = SessionLocal()
        self.scorer = TrendScorer()
        self.notifier = Notifier()
        self.consecutive_errors = 0
        
        logger.info(f"Sentinel started. Interval: {check_interval}s")
        init_db()

    async def run(self):
        """Main monitoring loop."""
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
        """Fetch and send new trending videos from Creative Center as ONE batch message."""
        
        logger.info("Fetching trending videos from Creative Center...")
        
        try:
            videos = await get_trending_videos_with_stats(
                sort_by="Like",
                count=20,
                headless=self.headless
            )
        except Exception as e:
            logger.error(f"Failed to fetch videos: {e}")
            raise e

        if not videos:
            logger.warning("No videos received from Creative Center.")
            return

        logger.info(f"Received {len(videos)} videos. Processing...")
        
        # Sort by engagement (views, then likes, then shares)
        videos_sorted = sorted(
            videos, 
            key=lambda v: (v.play_count, v.like_count, v.share_count), 
            reverse=True
        )
        
        now = datetime.utcnow()
        
        # Collect all video data and track which are NEW
        all_video_data = []
        new_video_ids = set()
        
        for video in videos_sorted:
            try:
                v_id = video.video_id
                author = video.author
                create_time = datetime.fromtimestamp(video.create_time)
                
                # Check if video already exists in database
                tracked_video = self.db.query(TrackedVideo).filter_by(video_id=v_id).first()
                is_new = tracked_video is None
                
                # Build video data dict
                stats = {
                    'playCount': video.play_count,
                    'diggCount': video.like_count,
                    'commentCount': video.comment_count,
                    'shareCount': video.share_count
                }
                
                video_data = {
                    'id': v_id,
                    'author': author,
                    'stats': stats,
                    'desc': video.description[:500] if video.description else "",
                    'permalink': video.video_url,
                    'create_time': create_time
                }
                
                all_video_data.append(video_data)
                
                if is_new:
                    new_video_ids.add(v_id)
                    logger.info(f"NEW VIDEO: {v_id} (@{author}) - {video.play_count:,} views")
                    
                    # Add to database
                    tracked_video = TrackedVideo(
                        video_id=v_id,
                        author_id=author,
                        created_at=create_time,
                        first_seen_at=now,
                        description=video.description[:500] if video.description else "",
                        permalink=video.video_url,
                        status='sent'
                    )
                    self.db.add(tracked_video)
                    self.db.flush()
                    
                    # Insert stats
                    new_stat = VideoStats(
                        video_id=tracked_video.id,
                        collected_at=now,
                        play_count=video.play_count,
                        digg_count=video.like_count,
                        share_count=video.share_count,
                        comment_count=video.comment_count,
                        calculated_velocity=0,
                        acceleration=0,
                        link=video.video_url
                    )
                    self.db.add(new_stat)
                    
            except Exception as e:
                logger.error(f"Error processing video {video.video_id}: {e}")
                continue
        
        self.db.commit()
        
        # Send ONE batch notification with all videos
        if new_video_ids:
            logger.info(f"Sending batch notification with {len(new_video_ids)} NEW videos...")
            self.notifier.notify_batch_videos(all_video_data, new_video_ids)
        else:
            logger.info("No new videos this cycle - skipping notification.")
        
        logger.info(f"Batch complete. {len(new_video_ids)} new videos found.")

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
