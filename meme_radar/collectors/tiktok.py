"""
TikTok collector using TikTokApi.

Uses browser cookies for authentication to bypass bot detection.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

from .base import BaseCollector, CollectionResult, CommentEvent, PostEvent

# Suppress noisy TikTokApi errors
logging.getLogger("TikTokApi.tiktok").setLevel(logging.CRITICAL)


class TikTokCollector(BaseCollector):
    """
    Collector for TikTok using TikTokApi.
    
    Uses exported browser cookies for reliable scraping.
    """
    
    PLATFORM_NAME = "tiktok"
    COOKIES_FILE = "tiktok_cookies.json"
    
    def __init__(self):
        super().__init__()
        self._api = None
        self._api_available = None
    
    def is_available(self) -> bool:
        """Check if TikTokApi and playwright are installed."""
        if self._api_available is None:
            try:
                from TikTokApi import TikTokApi
                self._api_available = True
            except ImportError:
                self._api_available = False
        return self._api_available
    
    def _get_cookies_path(self) -> Path:
        """Get path to cookies file."""
        # Look in project root
        return Path(__file__).parent.parent.parent / self.COOKIES_FILE
    
    def _load_cookies(self) -> Optional[Dict]:
        """
        Load cookies from JSON file.
        
        Expected format (from browser extension like EditThisCookie):
        [
            {"name": "sessionid", "value": "...", "domain": ".tiktok.com", ...},
            {"name": "msToken", "value": "...", "domain": ".tiktok.com", ...},
            ...
        ]
        """
        path = self._get_cookies_path()
        if not path.exists():
            return None
        
        try:
            with open(path, 'r') as f:
                cookies = json.load(f)
            
            # Convert to dict format TikTokApi expects
            cookie_dict = {}
            ms_token = None
            
            for cookie in cookies:
                name = cookie.get('name', '')
                value = cookie.get('value', '')
                if name and value:
                    cookie_dict[name] = value
                    if name == 'msToken':
                        ms_token = value
            
            print(f"[TikTok] Loaded {len(cookie_dict)} cookies from {self.COOKIES_FILE}")
            if ms_token:
                print(f"[TikTok] Found msToken: {ms_token[:30]}...")
            
            return {
                'cookies': cookie_dict,
                'ms_token': ms_token
            }
            
        except Exception as e:
            print(f"[TikTok] Failed to load cookies: {e}")
            return None
    
    async def _init_api(self, ms_token: Optional[str] = None, cookies: Optional[Dict] = None):
        """Initialize the TikTokApi with ms_token."""
        from TikTokApi import TikTokApi
        
        self._api = TikTokApi()
        
        # Use ms_token (either from cookies or config)
        ms_tokens = [ms_token] if ms_token else []
        
        # Simple session config
        session_config = {
            "ms_tokens": ms_tokens,
            "num_sessions": 1,
            "sleep_after": 3,
            "headless": True,
            "browser": "chromium",
        }
        
        # Create session
        await self._api.create_sessions(**session_config)
        print("[TikTok] Session created")
        
        return self._api
    
    def collect(self) -> CollectionResult:
        """Collect TikTok videos from users and hashtags."""
        import asyncio
        import sys
        
        result = CollectionResult(platform=self.PLATFORM_NAME)
        
        if not self.config.get("tiktok", "enabled", default=True):
            result.errors.append("TikTok collector is disabled")
            return result
        
        if not self.is_available():
            result.errors.append("TikTokApi not installed")
            return result
        
        # 1. Try to refresh token if needed (using new TokenManager)
        # from ..token_manager import get_token_manager
        # tm = get_token_manager()
        # This will use cached token, or refresh if expired (1 hour)
        # fresh_token = tm.get_token_sync()
        fresh_token = None
        
        # 2. Try to load cookies from file
        cookie_data = self._load_cookies()
        
        # 3. Determine best ms_token to use
        ms_token = None
        
        # Priority: Freshly refreshed > File cookies > Config
        if fresh_token:
            ms_token = fresh_token
            print(f"[TikTok] Using auto-refreshed msToken")
        elif cookie_data and cookie_data.get('ms_token'):
            ms_token = cookie_data['ms_token']
        else:
            ms_token = self.config.get("tiktok", "ms_token")
            
        cookies = cookie_data['cookies'] if cookie_data else None
        
        if ms_token:
            print(f"[TikTok] Found msToken: {ms_token[:30]}...")
        
        if not cookie_data and not ms_token:
            print("[TikTok] WARNING: No cookies or ms_token found!")
            print(f"[TikTok] Export your TikTok cookies to: {self._get_cookies_path()}")
        
        # Reset API
        self._api = None
        
        try:
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._collect_async(result, ms_token, cookies))
            finally:
                loop.close()
        except Exception as e:
            result.errors.append(f"Collection error: {str(e)}")
        
        result.completed_at = datetime.utcnow()
        return result
    
    async def _collect_async(self, result: CollectionResult, ms_token: Optional[str], cookies: Optional[Dict]) -> None:
        """Async collection from users and hashtags."""
        users = self.config.get("tiktok", "users", default=[])
        hashtags = self.config.get("tiktok", "hashtags", default=[])
        max_per_source = self.config.get("tiktok", "max_posts_per_source", default=20)
        max_age_days = self.config.get("tiktok", "max_video_age_days", default=7)
        
        # Calculate cutoff date for filtering old/pinned videos
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)
        
        try:
            api = await self._init_api(ms_token, cookies)
            
            # Collect from users
            for idx, username in enumerate(users):
                try:
                    # Add delay between accounts to avoid rate limiting (except first)
                    if idx > 0:
                        await asyncio.sleep(2)
                    
                    print(f"[TikTok] @{username}...")
                    user = api.user(username)
                    count = 0
                    skipped = 0
                    
                    # Add timeout for user video iteration
                    try:
                        async for video in user.videos(count=max_per_source + 10):
                            if count >= max_per_source:
                                break
                            try:
                                post = await self._process_video(video)
                                # Skip old/pinned videos
                                if post.created_at and post.created_at < cutoff_date:
                                    skipped += 1
                                    continue
                                result.posts.append(post)
                                count += 1
                            except Exception:
                                pass
                    except Exception as e:
                        # If iteration fails, might be temporary block
                        if count == 0:
                            print(f"[TikTok] @{username}: failed to fetch ({str(e)[:40]})")
                            result.errors.append(f"@{username}: fetch failed")
                            continue
                    
                    if count > 0:
                        msg = f"[TikTok] @{username}: {count} videos ✓"
                        if skipped > 0:
                            msg += f" (skipped {skipped} old)"
                        print(msg)
                    else:
                        print(f"[TikTok] @{username}: no videos")
                        result.errors.append(f"@{username}: no videos")
                except Exception as e:
                    error = str(e)[:60]
                    print(f"[TikTok] @{username}: {error}")
                    result.errors.append(f"@{username}: {error}")
            
            # Collect from hashtags
            for hashtag in hashtags:
                try:
                    print(f"[TikTok] #{hashtag}...")
                    tag = api.hashtag(name=hashtag)
                    count = 0
                    skipped = 0
                    async for video in tag.videos(count=max_per_source + 10):
                        if count >= max_per_source:
                            break
                        try:
                            post = await self._process_video(video)
                            # Skip old videos
                            if post.created_at and post.created_at < cutoff_date:
                                skipped += 1
                                continue
                            result.posts.append(post)
                            count += 1
                        except Exception:
                            pass
                    if count > 0:
                        msg = f"[TikTok] #{hashtag}: {count} videos ✓"
                        if skipped > 0:
                            msg += f" (skipped {skipped} old)"
                        print(msg)
                    else:
                        print(f"[TikTok] #{hashtag}: no videos")
                        result.errors.append(f"#{hashtag}: no videos")
                except Exception as e:
                    error = str(e)[:60]
                    print(f"[TikTok] #{hashtag}: {error}")
                    result.errors.append(f"#{hashtag}: {error}")
                    
        except Exception as e:
            result.errors.append(f"API error: {str(e)}")
        finally:
            if self._api:
                await self._api.close_sessions()
                self._api = None
    
    async def _process_video(self, video) -> PostEvent:
        """Convert a TikTok video to PostEvent."""
        info = video.as_dict
        
        caption = info.get('desc', '') or ''
        hashtags = self.extract_hashtags(caption)
        
        for challenge in info.get('challenges', []):
            if 'title' in challenge:
                hashtags.append(challenge['title'].lower())
        
        author_info = info.get('author', {})
        author = author_info.get('uniqueId') or author_info.get('nickname', '')
        
        stats = info.get('stats', {})
        likes = stats.get('diggCount', 0) or stats.get('heartCount', 0) or 0
        shares = stats.get('shareCount', 0) or 0
        comments = stats.get('commentCount', 0) or 0
        plays = stats.get('playCount', 0) or 0
        
        video_id = info.get('id', '')
        permalink = f"https://www.tiktok.com/@{author}/video/{video_id}" if author else None
        
        media_urls = []
        if 'video' in info and 'cover' in info['video']:
            media_urls.append((info['video']['cover'], 'video'))
        
        post = PostEvent(
            platform=self.PLATFORM_NAME,
            platform_post_id=video_id,
            author=author,
            created_at=datetime.utcfromtimestamp(info.get('createTime', 0)) if info.get('createTime') else None,
            text=caption,
            permalink=permalink,
            likes=likes,
            shares=shares,
            comments_count=comments,
            hashtags=list(set(hashtags)),
            media_urls=media_urls,
            raw_metadata={
                "play_count": plays,
                "music_title": info.get('music', {}).get('title'),
                "music_author": info.get('music', {}).get('authorName'),
            }
        )
        
        post.engagement_score = self.calculate_engagement_score(
            likes=likes, shares=shares, comments=comments, views=plays
        )
        
        return post


if __name__ == "__main__":
    collector = TikTokCollector()
    
    if not collector.is_available():
        print("TikTokApi not installed")
    else:
        print("Collecting...")
        result = collector.collect()
        print(f"\nGot {len(result.posts)} videos, {len(result.errors)} errors")
