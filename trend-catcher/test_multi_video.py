"""
Test scraping multiple videos to verify consistency
"""
import asyncio
from playwright.async_api import async_playwright

TEST_URLS = [
    "https://www.tiktok.com/@bookingcom/video/7579204322219625761",
    "https://www.tiktok.com/@qing.zeng/video/7580454676840172812",
    "https://www.tiktok.com/@tatyana.jade/video/7567081592141663496",
]

async def scrape_video(page, url):
    """Scrape a single video's metrics."""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        
        result = await page.evaluate("""
            () => {
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
                return null;
            }
        """)
        
        if result:
            stats = result.get('statsV2') or result.get('stats') or {}
            return {
                'id': result.get('id'),
                'author': result.get('author', {}).get('uniqueId') if isinstance(result.get('author'), dict) else result.get('author'),
                'createTime': result.get('createTime'),
                'playCount': stats.get('playCount'),
                'diggCount': stats.get('diggCount'),
                'commentCount': stats.get('commentCount'),
                'shareCount': stats.get('shareCount'),
            }
        return None
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None

async def test_multiple():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)  # Headless for speed
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        print("Testing multiple video URLs...\n")
        
        for url in TEST_URLS:
            result = await scrape_video(page, url)
            if result:
                print(f"✅ @{result['author']} - ID: {result['id']}")
                print(f"   Plays: {int(result['playCount']):,}")
                print(f"   Likes: {int(result['diggCount']):,}")
                print(f"   Comments: {int(result['commentCount']):,}")
                print(f"   Shares: {int(result['shareCount']):,}")
                print()
            else:
                print(f"❌ Failed: {url}\n")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_multiple())
