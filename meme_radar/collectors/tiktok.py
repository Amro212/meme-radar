"""
TikTok collector using TikTokApi.

Fetches trending videos and their comments to detect emerging memes.
"""

from datetime import datetime
from typing import Optional

from .base import BaseCollector, CollectionResult, CommentEvent, PostEvent


class TikTokCollector(BaseCollector):
    """
    Collector for TikTok using TikTokApi.
    
    Fetches trending videos and their top comments.
    Note: TikTokApi requires playwright for browser automation.
    """
    
    PLATFORM_NAME = "tiktok"
    
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
    
    async def _init_api(self):
        """Initialize the TikTokApi."""
        if self._api is None:
            from TikTokApi import TikTokApi
            self._api = TikTokApi()
            await self._api.create_sessions(
                num_sessions=1,
                sleep_after=3,
                headless=True,
            )
        return self._api
    
    def collect(self) -> CollectionResult:
        """
        Collect trending TikTok videos.
        
        Uses asyncio to run the async collection.
        """
        import asyncio
        
        result = CollectionResult(platform=self.PLATFORM_NAME)
        
        if not self.config.get("tiktok", "enabled", default=True):
            result.errors.append("TikTok collector is disabled in config")
            return result
        
        if not self.is_available():
            result.errors.append(
                "TikTokApi not installed. Install with: pip install TikTokApi playwright && playwright install"
            )
            return result
        
        try:
            # Run async collection
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._collect_async(result))
            finally:
                loop.close()
        except Exception as e:
            result.errors.append(f"TikTok collection error: {str(e)}")
        
        result.completed_at = datetime.utcnow()
        return result
    
    async def _collect_async(self, result: CollectionResult) -> None:
        """Async collection of trending videos."""
        from TikTokApi import TikTokApi
        
        trending_limit = self.config.get("tiktok", "trending_limit", default=100)
        comments_per_video = self.config.get("tiktok", "comments_per_video", default=20)
        
        try:
            api = await self._init_api()
            
            async for video in api.trending.videos(count=trending_limit):
                try:
                    post = await self._process_video(video)
                    result.posts.append(post)
                    
                    # Fetch comments
                    if comments_per_video > 0:
                        await self._collect_comments(video, post.platform_post_id, comments_per_video, result)
                        
                except Exception as e:
                    result.errors.append(f"Error processing video: {str(e)}")
                    
        except Exception as e:
            result.errors.append(f"TikTok API error: {str(e)}")
        finally:
            if self._api:
                await self._api.close_sessions()
                self._api = None
    
    async def _process_video(self, video) -> PostEvent:
        """Convert a TikTok video object to PostEvent."""
        video_info = video.as_dict
        
        # Extract caption/description
        caption = video_info.get('desc', '') or ''
        
        # Extract hashtags from challenges
        hashtags = self.extract_hashtags(caption)
        if 'challenges' in video_info:
            for challenge in video_info['challenges']:
                if 'title' in challenge:
                    hashtags.append(challenge['title'].lower())
        
        # Author info
        author_info = video_info.get('author', {})
        author = author_info.get('uniqueId') or author_info.get('nickname', '')
        
        # Stats
        stats = video_info.get('stats', {})
        likes = stats.get('diggCount', 0) or stats.get('heartCount', 0) or 0
        shares = stats.get('shareCount', 0) or 0
        comments_count = stats.get('commentCount', 0) or 0
        plays = stats.get('playCount', 0) or 0
        
        # Video URL
        video_id = video_info.get('id', '')
        permalink = f"https://www.tiktok.com/@{author}/video/{video_id}" if author else None
        
        # Media URL (cover image)
        media_urls = []
        if 'video' in video_info and 'cover' in video_info['video']:
            media_urls.append((video_info['video']['cover'], 'video'))
        
        post = PostEvent(
            platform=self.PLATFORM_NAME,
            platform_post_id=video_id,
            author=author,
            created_at=datetime.utcfromtimestamp(video_info.get('createTime', 0)) if video_info.get('createTime') else None,
            text=caption,
            permalink=permalink,
            likes=likes,
            shares=shares,
            comments_count=comments_count,
            hashtags=list(set(hashtags)),
            media_urls=media_urls,
            raw_metadata={
                "play_count": plays,
                "music_title": video_info.get('music', {}).get('title'),
                "music_author": video_info.get('music', {}).get('authorName'),
            }
        )
        
        post.engagement_score = self.calculate_engagement_score(
            likes=likes,
            shares=shares,
            comments=comments_count,
            views=plays,
        )
        
        return post
    
    async def _collect_comments(
        self,
        video,
        video_id: str,
        limit: int,
        result: CollectionResult,
    ) -> None:
        """Collect top comments from a video."""
        try:
            count = 0
            async for comment in video.comments(count=limit):
                if count >= limit:
                    break
                
                comment_info = comment.as_dict
                
                comment_event = CommentEvent(
                    platform_comment_id=comment_info.get('cid', ''),
                    author=comment_info.get('user', {}).get('unique_id', ''),
                    created_at=datetime.utcfromtimestamp(comment_info.get('create_time', 0)) if comment_info.get('create_time') else None,
                    text=comment_info.get('text', ''),
                    normalized_text=self.normalize_comment_text(comment_info.get('text', '')),
                    score=comment_info.get('digg_count', 0) or 0,
                )
                
                result.comments.append((video_id, comment_event))
                count += 1
                
        except Exception as e:
            # Don't fail the whole collection for comment errors
            pass


# Allow standalone testing
if __name__ == "__main__":
    collector = TikTokCollector()
    
    if not collector.is_available():
        print("TikTok collector not available. Install: pip install TikTokApi playwright && playwright install")
    else:
        print("Collecting from TikTok...")
        result = collector.collect()
        print(f"Collected {len(result.posts)} videos and {len(result.comments)} comments")
        
        if result.errors:
            print(f"Errors: {result.errors}")
        
        for post in result.posts[:3]:
            print(f"\n@{post.author}: {post.text[:80]}...")
            print(f"  Likes: {post.likes}, Shares: {post.shares}")
            print(f"  Hashtags: {post.hashtags}")
