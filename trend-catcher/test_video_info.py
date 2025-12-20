"""
Test TikTokApi video.info() with a complete URL from Creative Center scraper
"""
import asyncio
import os
import sys
sys.path.insert(0, "trend-catcher")

from TikTokApi import TikTokApi
from utils_auth import load_cookies

# Test with a video URL from Creative Center scraper output
TEST_VIDEO_URL = "https://www.tiktok.com/@bookingcom/video/7579204322219625761"

async def test_video_info():
    cookie_data = load_cookies()
    ms_token = cookie_data.get('ms_token') if cookie_data else None
    
    print(f"Testing video URL: {TEST_VIDEO_URL}")
    print(f"ms_token found: {ms_token is not None}")
    
    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=[ms_token],
            num_sessions=1,
            sleep_after=3,
            browser=os.getenv("TIKTOK_BROWSER", "chromium"),
            headless=False
        )
        
        try:
            video = api.video(url=TEST_VIDEO_URL)
            
            print("\nFetching video.info()...")
            info = await video.info()
            
            print("\n=== Video Info ===")
            print(f"ID: {info.get('id')}")
            print(f"Description: {info.get('desc', '')[:100]}...")
            print(f"Author: {info.get('author', {}).get('uniqueId')}")
            print(f"Create Time: {info.get('createTime')}")
            
            stats = info.get('stats', {})
            print(f"\n=== Stats ===")
            print(f"Plays: {stats.get('playCount', 'N/A'):,}" if stats.get('playCount') else "Plays: N/A")
            print(f"Likes: {stats.get('diggCount', 'N/A'):,}" if stats.get('diggCount') else "Likes: N/A")
            print(f"Comments: {stats.get('commentCount', 'N/A'):,}" if stats.get('commentCount') else "Comments: N/A")
            print(f"Shares: {stats.get('shareCount', 'N/A'):,}" if stats.get('shareCount') else "Shares: N/A")
            
            print("\n=== Full info keys ===")
            print(list(info.keys()))
            
            print("\nSUCCESS! api.video(url).info() works!")
            return info
            
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            return None

if __name__ == "__main__":
    asyncio.run(test_video_info())
