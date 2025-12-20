"""
Video Metrics Scraper

Scrapes engagement metrics from TikTok video pages using Playwright.
Parses the __UNIVERSAL_DATA_FOR_REHYDRATION__ script tag for video stats.
"""

import logging
from typing import Optional, Dict
from dataclasses import dataclass
from playwright.async_api import Page

logger = logging.getLogger("video_scraper")


@dataclass
class VideoMetrics:
    """Video engagement metrics."""
    video_id: str
    author: str
    description: str
    create_time: int
    play_count: int
    like_count: int
    comment_count: int
    share_count: int
    video_url: str


async def scrape_video_metrics(page: Page, url: str) -> Optional[VideoMetrics]:
    """
    Scrape engagement metrics from a TikTok video page.
    
    Uses the existing browser page context for efficiency.
    Parses __UNIVERSAL_DATA_FOR_REHYDRATION__ script tag.
    
    Args:
        page: Playwright page instance (reuse browser context)
        url: Full TikTok video URL
        
    Returns:
        VideoMetrics object with all engagement stats, or None if failed
    """
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)  # Wait for JS hydration
        
        result = await page.evaluate("""
            () => {
                // Try __UNIVERSAL_DATA_FOR_REHYDRATION__ (most reliable)
                const universalData = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
                if (universalData) {
                    try {
                        const data = JSON.parse(universalData.textContent);
                        const defaultScope = data.__DEFAULT_SCOPE__ || {};
                        const videoDetail = defaultScope['webapp.video-detail'] || {};
                        const itemInfo = videoDetail.itemInfo || {};
                        if (itemInfo.itemStruct) {
                            return itemInfo.itemStruct;
                        }
                    } catch (e) {}
                }
                
                // Fallback: Try SIGI_STATE
                const sigiState = document.getElementById('SIGI_STATE');
                if (sigiState) {
                    try {
                        const data = JSON.parse(sigiState.textContent);
                        const videoId = Object.keys(data.ItemModule || {})[0];
                        if (videoId && data.ItemModule[videoId]) {
                            return data.ItemModule[videoId];
                        }
                    } catch (e) {}
                }
                
                return null;
            }
        """)
        
        if not result:
            logger.warning(f"Could not extract video data from {url}")
            return None
        
        # Parse stats (try statsV2 first, then stats)
        stats = result.get('statsV2') or result.get('stats') or {}
        
        # Parse author (can be string or object)
        author = result.get('author', {})
        author_username = author.get('uniqueId', '') if isinstance(author, dict) else str(author)
        
        return VideoMetrics(
            video_id=result.get('id', ''),
            author=author_username,
            description=result.get('desc', ''),
            create_time=int(result.get('createTime', 0)),
            play_count=int(stats.get('playCount', 0)),
            like_count=int(stats.get('diggCount', 0)),
            comment_count=int(stats.get('commentCount', 0)),
            share_count=int(stats.get('shareCount', 0)),
            video_url=url
        )
        
    except Exception as e:
        logger.warning(f"Failed to scrape video metrics from {url}: {e}")
        return None


async def scrape_multiple_videos(page: Page, urls: list[str]) -> list[VideoMetrics]:
    """
    Scrape metrics for multiple videos using the same browser page.
    
    Args:
        page: Playwright page instance
        urls: List of TikTok video URLs
        
    Returns:
        List of VideoMetrics objects
    """
    results = []
    for url in urls:
        metrics = await scrape_video_metrics(page, url)
        if metrics:
            results.append(metrics)
            logger.info(f"Scraped @{metrics.author}: {metrics.play_count:,} plays, {metrics.share_count:,} shares")
    return results
