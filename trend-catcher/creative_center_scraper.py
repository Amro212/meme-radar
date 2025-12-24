"""
Creative Center Video Scraper

Scrapes trending video IDs from TikTok Creative Center page.
Videos are sorted by engagement metrics (shares, likes, comments, hot).
Uses TikTok oEmbed API to get author usernames.
"""

import asyncio
import aiohttp
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
from playwright.async_api import async_playwright, Page

from stealth_browser import create_stealth_browser, add_stealth_scripts

from video_scraper import scrape_video_metrics, VideoMetrics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("creative_center_scraper")

# TikTok Creative Center URL for popular videos
CREATIVE_CENTER_URL = "https://ads.tiktok.com/business/creativecenter/inspiration/popular/pc/en"

# TikTok oEmbed API endpoint
OEMBED_API = "https://www.tiktok.com/oembed"


@dataclass
class VideoInfo:
    """Video info extracted from Creative Center + oEmbed."""
    video_id: str
    author_username: str
    author_url: str
    video_url: str
    title: str = ""
    thumbnail_url: str = ""


async def fetch_oembed_info(video_id: str) -> Optional[Dict]:
    """
    Fetch video info from TikTok oEmbed API.
    Works with any dummy username in the URL.
    """
    try:
        # TikTok will resolve the correct author regardless of the username used
        dummy_url = f"https://www.tiktok.com/@a/video/{video_id}"
        oembed_url = f"{OEMBED_API}?url={dummy_url}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(oembed_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    logger.warning(f"oEmbed returned status {response.status} for video {video_id}")
                    return None
    except Exception as e:
        logger.warning(f"Failed to fetch oEmbed for video {video_id}: {e}")
        return None


async def get_trending_videos(
    sort_by: str = "Shares",
    period: str = "120",
    count: int = 20,
    headless: bool = True,
    max_retries: int = 3
) -> List[VideoInfo]:
    """
    Scrape trending videos from TikTok Creative Center with retry logic.
    
    Args:
        sort_by: Sort option - "hot", "Like", "Comments", or "Shares"
        period: Time period - "7", "30", or "120" days
        count: Target number of videos to retrieve
        headless: Run browser in headless mode
        max_retries: Maximum retry attempts if bot detection occurs
        
    Returns:
        List of VideoInfo objects with video IDs, author info, and URLs
    """
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Scraping attempt {attempt + 1}/{max_retries}")
            videos = await _scrape_creative_center(sort_by, period, count, headless)
            
            if videos:
                logger.info(f"Successfully scraped {len(videos)} videos on attempt {attempt + 1}")
                return videos
            else:
                if attempt < max_retries - 1:
                    backoff_time = (2 ** attempt) * 5  # 5s, 10s, 20s
                    logger.warning(f"No videos loaded (likely bot detection). Retrying in {backoff_time}s...")
                    await asyncio.sleep(backoff_time)
                else:
                    logger.error(f"Failed to load videos after {max_retries} attempts")
                    return []
                    
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                backoff_time = (2 ** attempt) * 5
                logger.info(f"Retrying in {backoff_time}s...")
                await asyncio.sleep(backoff_time)
            else:
                logger.error(f"All {max_retries} attempts failed")
                return []
    
    return []


async def _scrape_creative_center(
    sort_by: str,
    period: str,
    count: int,
    headless: bool
) -> List[VideoInfo]:
    """Internal function that performs the actual scraping."""
    video_ids = []
    
    try:
        async with async_playwright() as p:
            # Use stealth browser to evade bot detection
            browser, context = await create_stealth_browser(p, headless=headless)
            page = await context.new_page()
            await add_stealth_scripts(page)
            
            logger.info(f"Navigating to TikTok Creative Center...")
            await page.goto(CREATIVE_CENTER_URL, wait_until="domcontentloaded", timeout=60000)
            
            # Wait for network to be idle (JavaScript loaded)
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
                logger.info("Network idle achieved")
            except:
                logger.warning("Network idle timeout - continuing anyway")
            
            # Wait for videos to load (critical fix for reliability)
            logger.info("Waiting for video elements to load...")
            max_wait_attempts = 30  # Up to 60 seconds (30 × 2s)
            for attempt in range(max_wait_attempts):
                await page.wait_for_timeout(2000)  # 2s between checks
                
                video_count = await page.evaluate("""
                    () => document.querySelectorAll('blockquote[data-video-id]').length
                """)
                
                if video_count > 0:
                    logger.info(f"Videos loaded ({video_count} videos found after {(attempt + 1) * 2}s)")
                    break
                    
                if attempt == max_wait_attempts - 1:
                    logger.warning(f"No videos loaded after {max_wait_attempts * 2}s - page may not have content")
            
            # Additional stabilization wait
            await page.wait_for_timeout(3000)
            
            # Sort by the requested metric (e.g., Shares)
            await _select_sort_option(page, sort_by)
            
            # Wait for page to stabilize after sort change (page may navigate/reload)
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except:
                pass  # Timeout is fine, just continue
            
            # Scroll back to top where videos are located
            await page.evaluate("window.scrollTo(0, 400)")
            await page.wait_for_timeout(5000)
            
            # Click "View more" to load more videos
            await _load_more_videos(page, target_count=count)
            
            # Extract video IDs
            video_ids = await _extract_video_ids(page)
            
            await browser.close()
            
    except Exception as e:
        logger.error(f"Failed to scrape Creative Center: {e}")
        import traceback
        traceback.print_exc()
    
    logger.info(f"Retrieved {len(video_ids)} video IDs")
    
    # Fetch author info via oEmbed API
    videos = []
    for vid in video_ids[:count]:
        oembed_data = await fetch_oembed_info(vid)
        if oembed_data:
            author_url = oembed_data.get('author_url', '')
            author_username = author_url.split('/@')[-1].split('/')[0].split('?')[0] if '@' in author_url else ''
            
            videos.append(VideoInfo(
                video_id=vid,
                author_username=author_username,
                author_url=author_url,
                video_url=f"https://www.tiktok.com/@{author_username}/video/{vid}",
                title=oembed_data.get('title', ''),
                thumbnail_url=oembed_data.get('thumbnail_url', '')
            ))
            logger.info(f"Fetched oEmbed for {vid}: @{author_username}")
        else:
            # Fallback: include video ID without author info
            videos.append(VideoInfo(
                video_id=vid,
                author_username="unknown",
                author_url="",
                video_url=f"https://www.tiktok.com/video/{vid}"
            ))
    
    return videos


async def _select_sort_option(page: Page, sort_by: str):
    """Select the sort option from the 'Sort by' dropdown (on the right side)."""
    try:
        logger.info(f"Selecting sort option: {sort_by}")
        
        # Wait for page content to load
        await page.wait_for_timeout(5000)
        
        # Scroll down slightly to ensure dropdown is visible
        await page.evaluate("window.scrollBy(0, 400)")
        await page.wait_for_timeout(1000)
        
        # Find the 'Sort by' dropdown coordinates - it's the 'hot' element near 'Sort by' text
        coords = await page.evaluate("""
            () => {
                const allElements = Array.from(document.querySelectorAll('div, span'));
                
                // Find 'Sort by' text first
                const sortByEl = allElements.find(el => 
                    el.innerText && el.innerText.trim() === 'Sort by' && el.offsetParent !== null
                );
                
                if (!sortByEl) return null;
                const sortByRect = sortByEl.getBoundingClientRect();
                
                // Find 'hot' that's vertically aligned with 'Sort by' (within 50px)
                const hotEls = allElements.filter(el => 
                    el.innerText && 
                    el.innerText.trim() === 'hot' && 
                    el.offsetParent !== null
                );
                
                for (const hot of hotEls) {
                    const hotRect = hot.getBoundingClientRect();
                    // Must be within 50px vertically of Sort by
                    if (Math.abs(hotRect.top - sortByRect.top) < 50) {
                        return {
                            x: hotRect.left + hotRect.width / 2,
                            y: hotRect.top + hotRect.height / 2,
                            sortByX: sortByRect.left
                        };
                    }
                }
                
                return null;
            }
        """)
        
        if coords:
            logger.info(f"Found Sort by dropdown at ({coords['x']:.0f}, {coords['y']:.0f}), Sort by label at x={coords['sortByX']:.0f}")
            
            # Use Playwright's mouse.click for reliable clicking
            await page.mouse.click(coords['x'], coords['y'])
            logger.info("Clicked Sort by dropdown")
        else:
            logger.warning("Could not find Sort by dropdown")
            return
        
        # Wait for dropdown animation
        await page.wait_for_timeout(1500)
        
        # Find the target option (Shares) coordinates and click it
        option_coords = await page.evaluate(f"""
            () => {{
                const options = document.querySelectorAll('.byted-select-option');
                for (const opt of options) {{
                    if (opt.innerText && opt.innerText.trim() === '{sort_by}') {{
                        const rect = opt.getBoundingClientRect();
                        return {{
                            x: rect.left + rect.width / 2,
                            y: rect.top + rect.height / 2,
                            text: opt.innerText.trim()
                        }};
                    }}
                }}
                return null;
            }}
        """)
        
        if option_coords:
            logger.info(f"Found '{option_coords['text']}' option at ({option_coords['x']:.0f}, {option_coords['y']:.0f})")
            await page.mouse.click(option_coords['x'], option_coords['y'])
            logger.info(f"Clicked {sort_by} option")
        else:
            logger.warning(f"{sort_by} option not found in dropdown")
        await page.wait_for_timeout(3000)
        
    except Exception as e:
        logger.warning(f"Failed to select sort option: {e}")


async def _select_time_period(page: Page, period: str):
    """Select the time period from the dropdown (on the LEFT side)."""
    try:
        period_map = {
            "7": "Last 7 days",
            "30": "Last 30 days",
            "120": "Last 120 days"
        }
        target_text = period_map.get(period, "Last 120 days")
        
        logger.info(f"Selecting time period: {target_text}")
        
        # The time period dropdown is on the LEFT side of the page (x < 300)
        open_result = await page.evaluate("""
            () => {
                const allElements = Array.from(document.querySelectorAll('div, span'));
                
                // Find elements with "days" that are on the left side
                const dayElements = allElements.filter(el => 
                    el.innerText && 
                    el.innerText.includes('days') && 
                    el.offsetParent !== null
                );
                
                for (const el of dayElements) {
                    const rect = el.getBoundingClientRect();
                    // Only click if it's on the left side (x < 400)
                    if (rect.left < 400 && rect.width < 200) {
                        el.click();
                        return 'Clicked time period dropdown at x=' + rect.left;
                    }
                }
                
                return 'Time period dropdown not found';
            }
        """)
        logger.info(f"Time period open result: {open_result}")
        
        await page.wait_for_timeout(1000)
        
        # Click the target period option
        select_result = await page.evaluate(f"""
            () => {{
                const options = document.querySelectorAll('.byted-select-option');
                for (const opt of options) {{
                    if (opt.innerText && opt.innerText.includes('{target_text}')) {{
                        opt.click();
                        return 'Selected ' + opt.innerText.trim();
                    }}
                }}
                return '{target_text} not found';
            }}
        """)
        
        logger.info(f"Time period selection result: {select_result}")
        await page.wait_for_timeout(2000)
        
    except Exception as e:
        logger.warning(f"Failed to select time period: {e}")


async def _load_more_videos(page: Page, target_count: int = 20):
    """Click 'View more' button to load additional videos."""
    try:
        max_clicks = 5  # Limit clicks to avoid infinite loops
        
        for i in range(max_clicks):
            # Count current videos using blockquotes with video-id
            current_count = await page.evaluate("""
                () => document.querySelectorAll('blockquote[data-video-id]').length
            """)
            logger.info(f"Current video count: {current_count}")
            
            if current_count >= target_count:
                break
            
            # Scroll to bottom to find View More button
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight - 500)")
            await page.wait_for_timeout(1000)
            
            # Click "View more" button using JS
            result = await page.evaluate("""
                () => {
                    const allElements = Array.from(document.querySelectorAll('*'));
                    const viewMore = allElements.find(el => 
                        el.innerText && 
                        el.innerText.trim() === 'View More' && 
                        el.offsetParent !== null &&
                        el.tagName !== 'SCRIPT'
                    );
                    if (viewMore) {
                        viewMore.click();
                        return 'Clicked View More';
                    }
                    return 'View More not found';
                }
            """)
            
            logger.info(f"View More result: {result}")
            
            if 'not found' in result:
                break
                
            await page.wait_for_timeout(2000)
                
    except Exception as e:
        logger.warning(f"Error loading more videos: {e}")


async def _extract_video_ids(page: Page) -> List[str]:
    """Extract video IDs from the page."""
    video_ids = []
    
    try:
        # Find all blockquote elements with data-video-id attribute
        result = await page.evaluate("""
            () => {
                const blockquotes = document.querySelectorAll('blockquote[data-video-id]');
                return Array.from(blockquotes).map(bq => bq.getAttribute('data-video-id'));
            }
        """)
        
        video_ids = [vid for vid in result if vid]
        logger.info(f"Extracted {len(video_ids)} video IDs from blockquotes")
        
    except Exception as e:
        logger.error(f"Failed to extract video IDs: {e}")
    
    return video_ids


# CLI for testing
async def get_trending_videos_with_stats(
    sort_by: str = "Shares",
    count: int = 10,
    headless: bool = True
) -> List[VideoMetrics]:
    """
    Get trending videos from Creative Center WITH engagement stats.
    
    This is the main entry point for the trend pipeline.
    1. Scrapes video IDs from Creative Center (sorted by shares)
    2. Fetches author info via oEmbed
    3. Scrapes each video page for full engagement metrics
    
    Args:
        sort_by: Sort metric ("Shares", "Like", "Comments", "hot")
        count: Number of videos to fetch
        headless: Run browser in headless mode
        
    Returns:
        List of VideoMetrics objects with full engagement data
    """
    # Step 1: Get video URLs from Creative Center
    videos = await get_trending_videos(
        sort_by=sort_by,
        count=count,
        headless=headless
    )
    
    if not videos:
        logger.warning("No videos found from Creative Center")
        return []
    
    logger.info(f"Got {len(videos)} videos from Creative Center, fetching stats...")
    
    # Step 2: Scrape metrics from each video page
    results = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        for video in videos:
            metrics = await scrape_video_metrics(page, video.video_url)
            if metrics:
                results.append(metrics)
                logger.info(f"  @{metrics.author}: {metrics.play_count:,} plays, {metrics.share_count:,} shares")
            else:
                logger.warning(f"  Failed to get metrics for {video.video_url}")
        
        await browser.close()
    
    logger.info(f"Successfully fetched metrics for {len(results)}/{len(videos)} videos")
    return results


if __name__ == "__main__":
    async def main():
        # Test the full pipeline
        videos = await get_trending_videos_with_stats(
            sort_by="Like",
            count=5,
            headless=False
        )
        
        print(f"\n=== Found {len(videos)} videos with stats ===")
        for i, video in enumerate(videos, 1):
            print(f"\n{i}. @{video.author}")
            print(f"   Plays: {video.play_count:,}")
            print(f"   Likes: {video.like_count:,}")
            print(f"   Comments: {video.comment_count:,}")
            print(f"   Shares: {video.share_count:,}")
            print(f"   URL: {video.video_url}")
    
    asyncio.run(main())
