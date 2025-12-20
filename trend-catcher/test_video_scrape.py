"""
Test direct scraping of TikTok video page for metrics
"""
import asyncio
import json
import re
from playwright.async_api import async_playwright

TEST_VIDEO_URL = "https://www.tiktok.com/@bookingcom/video/7579204322219625761"

async def scrape_video_metrics(url: str):
    """Scrape video metrics directly from TikTok video page."""
    print(f"Scraping: {url}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(5000)  # Wait for JS to load
        
        # Try to extract data from script tags
        result = await page.evaluate("""
            () => {
                // Method 1: Try SIGI_STATE
                const sigiState = document.getElementById('SIGI_STATE');
                if (sigiState) {
                    try {
                        const data = JSON.parse(sigiState.textContent);
                        const videoId = Object.keys(data.ItemModule || {})[0];
                        if (videoId && data.ItemModule[videoId]) {
                            return {
                                source: 'SIGI_STATE',
                                video: data.ItemModule[videoId]
                            };
                        }
                    } catch (e) {}
                }
                
                // Method 2: Try __UNIVERSAL_DATA_FOR_REHYDRATION__
                const universalData = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
                if (universalData) {
                    try {
                        const data = JSON.parse(universalData.textContent);
                        const defaultScope = data.__DEFAULT_SCOPE__ || {};
                        const videoDetail = defaultScope['webapp.video-detail'] || {};
                        const itemInfo = videoDetail.itemInfo || {};
                        if (itemInfo.itemStruct) {
                            return {
                                source: '__UNIVERSAL_DATA_FOR_REHYDRATION__',
                                video: itemInfo.itemStruct
                            };
                        }
                    } catch (e) {}
                }
                
                // Method 3: Look for any script with video data
                const scripts = document.querySelectorAll('script[type="application/json"]');
                for (const script of scripts) {
                    try {
                        const data = JSON.parse(script.textContent);
                        if (data && typeof data === 'object') {
                            // Look for stats or video info
                            const jsonStr = JSON.stringify(data);
                            if (jsonStr.includes('playCount') || jsonStr.includes('diggCount')) {
                                return {
                                    source: 'other_script',
                                    data: data
                                };
                            }
                        }
                    } catch (e) {}
                }
                
                // Method 4: Look for visible stats on page
                const statsElements = [];
                const allElements = document.querySelectorAll('[data-e2e*="count"], [class*="stat"], [class*="count"]');
                allElements.forEach(el => {
                    if (el.innerText && /\\d+[KMB]?/.test(el.innerText)) {
                        statsElements.push({
                            className: el.className,
                            text: el.innerText.trim(),
                            dataE2e: el.getAttribute('data-e2e')
                        });
                    }
                });
                
                return {
                    source: 'dom_scrape',
                    statsElements: statsElements,
                    pageTitle: document.title
                };
            }
        """)
        
        print(f"\nData source: {result.get('source')}")
        
        if result.get('video'):
            video = result['video']
            print(f"\n=== Video Info ===")
            print(f"ID: {video.get('id')}")
            print(f"Description: {video.get('desc', '')[:100]}...")
            print(f"Author: {video.get('author', {}).get('uniqueId') if isinstance(video.get('author'), dict) else video.get('author')}")
            print(f"Create Time: {video.get('createTime')}")
            
            stats = video.get('statsV2') or video.get('stats') or {}
            print(f"\n=== Stats ===")
            print(f"Plays: {stats.get('playCount', 'N/A')}")
            print(f"Likes: {stats.get('diggCount', 'N/A')}")
            print(f"Comments: {stats.get('commentCount', 'N/A')}")
            print(f"Shares: {stats.get('shareCount', 'N/A')}")
            
            return video
        else:
            print(f"\n=== Fallback: DOM elements ===")
            for el in result.get('statsElements', []):
                print(f"  {el.get('dataE2e', el.get('className'))}: {el.get('text')}")
            return result
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_video_metrics(TEST_VIDEO_URL))
