"""
Test multiple hashtags to confirm hashtag.videos() is broken
"""
import asyncio
import os
import sys
sys.path.insert(0, "trend-catcher")

from TikTokApi import TikTokApi
from utils_auth import load_cookies

async def test_multiple_hashtags():
    cookie_data = load_cookies()
    ms_token = cookie_data.get('ms_token') if cookie_data else None
    
    hashtags_to_test = ["fyp", "viral", "tiktok", "meme", "christmas"]
    
    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=[ms_token],
            num_sessions=1,
            sleep_after=3,
            browser="chromium",
            headless=False
        )
        
        for tag_name in hashtags_to_test:
            try:
                tag = api.hashtag(name=tag_name)
                
                # Get info first to verify hashtag exists
                info = await tag.info()
                view_count = info.get('challengeInfo', {}).get('stats', {}).get('viewCount', 'N/A')
                print(f"\n#{tag_name}: Views={view_count}")
                
                # Try to get videos
                count = 0
                async for video in tag.videos(count=5):
                    count += 1
                print(f"  Videos fetched: {count}")
                
            except Exception as e:
                print(f"  ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test_multiple_hashtags())
