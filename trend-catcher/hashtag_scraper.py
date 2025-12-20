"""
Hashtag Scraper Module

Scrapes trending hashtags from TikTok Creative Center using Playwright.
"""

import asyncio
import logging
from typing import List, Optional
from playwright.async_api import async_playwright, Browser, Page

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hashtag_scraper")

# TikTok Creative Center URL for trending hashtags
CREATIVE_CENTER_URL = "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en"

# Fallback hashtags if scraping fails
FALLBACK_HASHTAGS = [
    "fyp", "viral", "trending", "foryou", "foryoupage",
    "tiktok", "funny", "meme", "comedy", "dance"
]


async def get_trending_hashtags(
    headless: bool = True,
    max_hashtags: int = 10,
    period: str = "120"  # "7", "30", "120" days
) -> List[str]:
    """
    Scrape trending hashtags from TikTok Creative Center.
    
    Args:
        headless: Run browser in headless mode
        max_hashtags: Maximum number of hashtags to return
        period: Time period filter ("7", "30", or "120" days)
        
    Returns:
        List of hashtag names (without the # prefix)
    """
    hashtags = []
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            logger.info(f"Navigating to TikTok Creative Center...")
            await page.goto(CREATIVE_CENTER_URL, wait_until="networkidle", timeout=30000)
            
            # Wait for hashtag list to load
            await page.wait_for_timeout(3000)
            
            # Try to click the time period dropdown and select the desired period
            await _select_time_period(page, period)
            
            # Wait for content to update after filter change
            await page.wait_for_timeout(2000)
            
            # Scroll to load more hashtags
            await _scroll_to_load_more(page)
            
            # Extract hashtags
            hashtags = await _extract_hashtags(page, max_hashtags)
            
            await browser.close()
            
    except Exception as e:
        logger.error(f"Failed to scrape hashtags: {e}")
    
    # Use fallback if scraping failed
    if not hashtags:
        logger.warning("Using fallback hashtags")
        hashtags = FALLBACK_HASHTAGS[:max_hashtags]
    
    logger.info(f"Retrieved {len(hashtags)} hashtags: {hashtags}")
    return hashtags


async def _select_time_period(page: Page, period: str):
    """Click the time period dropdown and select the desired period."""
    try:
        period_map = {
            "7": "Last 7 days",
            "30": "Last 30 days", 
            "120": "Last 120 days"
        }
        target_text = period_map.get(period, "Last 120 days")
        
        # Find and click the dropdown trigger (usually shows current selection)
        dropdown_selectors = [
            "text=Last 7 days",
            "text=Last 30 days",
            "text=Last 120 days",
            "[class*='select']",
            "[class*='dropdown']"
        ]
        
        clicked = False
        for selector in dropdown_selectors:
            try:
                element = page.locator(selector).first
                if await element.is_visible(timeout=2000):
                    await element.click()
                    clicked = True
                    logger.info(f"Clicked dropdown using selector: {selector}")
                    break
            except:
                continue
        
        if not clicked:
            logger.warning("Could not find dropdown to click")
            return
            
        # Wait for dropdown options to appear
        await page.wait_for_timeout(1000)
        
        # Click the target period option
        try:
            option = page.locator(f"text={target_text}").first
            if await option.is_visible(timeout=2000):
                await option.click()
                logger.info(f"Selected period: {target_text}")
                await page.wait_for_timeout(2000)
        except Exception as e:
            logger.warning(f"Could not select period {target_text}: {e}")
            
    except Exception as e:
        logger.warning(f"Time period selection failed: {e}")


async def _scroll_to_load_more(page: Page, scroll_count: int = 5):
    """Scroll down the page to trigger lazy loading of more hashtags."""
    try:
        for i in range(scroll_count):
            await page.evaluate("window.scrollBy(0, 500)")
            await page.wait_for_timeout(500)
        logger.info(f"Scrolled {scroll_count} times to load more content")
    except Exception as e:
        logger.warning(f"Scroll failed: {e}")


async def _extract_hashtags(page: Page, max_count: int) -> List[str]:
    """Extract hashtag names from the page."""
    hashtags = []
    
    def add_tag(tag: str) -> bool:
        """Add tag if valid and not duplicate. Returns True if added."""
        tag = tag.strip().lower()
        if tag and tag not in hashtags and len(tag) > 1 and len(tag) < 50:
            hashtags.append(tag)
            return len(hashtags) >= max_count
        return False
    
    try:
        # Strategy 1: Look for spans containing hashtags with # prefix
        spans = await page.query_selector_all("span")
        for span in spans:
            text = await span.inner_text()
            text = text.strip()
            if text.startswith("#") and len(text) > 1:
                tag = text[1:]  # Remove the # prefix
                if add_tag(tag):
                    break
        
        # Strategy 2: Look for links containing /hashtag/ in href
        if len(hashtags) < max_count:
            links = await page.query_selector_all("a[href*='/hashtag/']")
            for link in links:
                href = await link.get_attribute("href")
                if href:
                    # Extract hashtag from URL like /hashtag/fnaf
                    parts = href.split("/hashtag/")
                    if len(parts) > 1:
                        tag = parts[1].split("/")[0].split("?")[0]
                        if add_tag(tag):
                            break
        
        # Strategy 3: Use JavaScript to find all text nodes with #
        if len(hashtags) < max_count:
            js_result = await page.evaluate("""
                () => {
                    const hashtags = [];
                    const walker = document.createTreeWalker(
                        document.body,
                        NodeFilter.SHOW_TEXT
                    );
                    while (walker.nextNode()) {
                        const text = walker.currentNode.textContent.trim();
                        if (text.startsWith('#') && text.length > 1 && text.length < 50) {
                            const tag = text.substring(1).trim().toLowerCase();
                            if (tag && !hashtags.includes(tag)) {
                                hashtags.push(tag);
                            }
                        }
                    }
                    return hashtags;
                }
            """)
            for tag in js_result:
                if add_tag(tag):
                    break
                        
    except Exception as e:
        logger.error(f"Hashtag extraction failed: {e}")
    
    return hashtags[:max_count]


# CLI for testing
if __name__ == "__main__":
    async def main():
        hashtags = await get_trending_hashtags(headless=False, max_hashtags=15, period="120")
        print(f"\nFound {len(hashtags)} hashtags:")
        for i, tag in enumerate(hashtags, 1):
            print(f"  {i}. #{tag}")
    
    asyncio.run(main())
