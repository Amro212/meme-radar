"""
Instagram collector using Instaloader.

Monitors configured hashtags and accounts for meme content.
"""

from datetime import datetime
from typing import Optional

from .base import BaseCollector, CollectionResult, CommentEvent, PostEvent


class InstagramCollector(BaseCollector):
    """
    Collector for Instagram using Instaloader.
    
    Monitors configured hashtags and accounts.
    Note: Instagram requires careful rate limiting to avoid blocks.
    """
    
    PLATFORM_NAME = "instagram"
    
    def __init__(self):
        super().__init__()
        self._loader = None
        self._loader_available = None
    
    def is_available(self) -> bool:
        """Check if instaloader is installed."""
        if self._loader_available is None:
            try:
                import instaloader
                self._loader_available = True
            except ImportError:
                self._loader_available = False
        return self._loader_available
    
    @property
    def loader(self):
        """Lazy-load the Instaloader instance."""
        if self._loader is None:
            import instaloader
            import os
            
            self._loader = instaloader.Instaloader(
                download_pictures=False,
                download_videos=False,
                download_video_thumbnails=False,
                download_geotags=False,
                download_comments=True,
                save_metadata=False,
                compress_json=False,
            )
            
            # Attempt login if credentials are provided
            username = self.config.get("instagram", "username")
            password = self.config.get("instagram", "password")
            
            print(f"[Instagram] Username from config: '{username}'")
            
            if username and password:
                # Try to load existing session first
                session_file = f".instaloader-session-{username}"
                try:
                    if os.path.exists(session_file):
                        self._loader.load_session_from_file(username, session_file)
                        print(f"[Instagram] Loaded existing session for {username}")
                    else:
                        print(f"[Instagram] No session file found, attempting login...")
                        self._loader.login(username, password)
                        self._loader.save_session_to_file(session_file)
                        print(f"[Instagram] Successfully logged in as {username}")
                except instaloader.exceptions.BadCredentialsException:
                    print(f"[Instagram] ERROR: Bad credentials for {username}")
                except instaloader.exceptions.TwoFactorAuthRequiredException:
                    print(f"[Instagram] ERROR: Two-factor auth required. Please disable 2FA or use app password.")
                except instaloader.exceptions.ConnectionException as e:
                    print(f"[Instagram] ERROR: Connection error during login: {e}")
                except Exception as e:
                    print(f"[Instagram] ERROR: Login failed: {type(e).__name__}: {e}")
            else:
                print("[Instagram] WARNING: No credentials configured. Hashtag scraping requires login.")
                
        return self._loader
    
    def collect(self) -> CollectionResult:
        """
        Collect posts from configured hashtags and accounts.
        """
        import time
        
        result = CollectionResult(platform=self.PLATFORM_NAME)
        
        if not self.config.get("instagram", "enabled", default=True):
            result.errors.append("Instagram collector is disabled in config")
            return result
        
        if not self.is_available():
            result.errors.append(
                "instaloader not installed. Install with: pip install instaloader"
            )
            return result
        
        hashtags = self.config.get("instagram", "hashtags", default=[])
        accounts = self.config.get("instagram", "accounts", default=[])
        max_posts = self.config.get("instagram", "max_posts_per_hashtag", default=50)
        request_delay = self.config.get("instagram", "request_delay", default=2)
        
        # Collect from hashtags
        for hashtag in hashtags:
            try:
                self._collect_hashtag(hashtag, max_posts, result)
                time.sleep(request_delay)  # Rate limiting
            except Exception as e:
                result.errors.append(f"Error collecting #{hashtag}: {str(e)}")
        
        # Collect from accounts
        for account in accounts:
            try:
                self._collect_account(account, max_posts, result)
                time.sleep(request_delay)  # Rate limiting
            except Exception as e:
                result.errors.append(f"Error collecting @{account}: {str(e)}")
        
        result.completed_at = datetime.utcnow()
        return result
    
    def _collect_hashtag(
        self,
        hashtag: str,
        max_posts: int,
        result: CollectionResult,
    ) -> None:
        """Collect posts from a hashtag."""
        import instaloader
        
        try:
            hashtag_obj = instaloader.Hashtag.from_name(self.loader.context, hashtag)
            
            count = 0
            for post in hashtag_obj.get_posts():
                if count >= max_posts:
                    break
                
                self._process_post(post, result)
                count += 1
                
        except Exception as e:
            result.errors.append(f"Hashtag #{hashtag} error: {str(e)}")
    
    def _collect_account(
        self,
        username: str,
        max_posts: int,
        result: CollectionResult,
    ) -> None:
        """Collect posts from an account."""
        import instaloader
        
        try:
            profile = instaloader.Profile.from_username(self.loader.context, username)
            
            count = 0
            for post in profile.get_posts():
                if count >= max_posts:
                    break
                
                self._process_post(post, result)
                count += 1
                
        except Exception as e:
            result.errors.append(f"Account @{username} error: {str(e)}")
    
    def _process_post(self, post, result: CollectionResult) -> None:
        """Process a single Instagram post."""
        # Extract caption
        caption = post.caption or ''
        
        # Extract hashtags
        hashtags = self.extract_hashtags(caption)
        if hasattr(post, 'caption_hashtags') and post.caption_hashtags:
            hashtags = list(set(hashtags + [tag.lower() for tag in post.caption_hashtags]))
        
        # Media URLs
        media_urls = []
        if post.is_video:
            if post.video_url:
                media_urls.append((post.video_url, 'video'))
        else:
            if post.url:
                media_urls.append((post.url, 'image'))
        
        # Handle carousel posts
        if hasattr(post, 'get_sidecar_nodes'):
            try:
                for node in post.get_sidecar_nodes():
                    if node.is_video:
                        media_urls.append((node.video_url, 'video'))
                    else:
                        media_urls.append((node.display_url, 'image'))
            except Exception:
                pass
        
        post_event = PostEvent(
            platform=self.PLATFORM_NAME,
            platform_post_id=post.shortcode,
            author=post.owner_username if hasattr(post, 'owner_username') else None,
            created_at=post.date_utc if hasattr(post, 'date_utc') else None,
            text=caption,
            permalink=f"https://www.instagram.com/p/{post.shortcode}/",
            likes=post.likes if hasattr(post, 'likes') else 0,
            shares=0,  # Instagram doesn't expose share count
            comments_count=post.comments if hasattr(post, 'comments') else 0,
            hashtags=hashtags,
            media_urls=media_urls,
            raw_metadata={
                "is_video": post.is_video,
                "video_view_count": post.video_view_count if hasattr(post, 'video_view_count') and post.is_video else None,
                "location": str(post.location) if hasattr(post, 'location') and post.location else None,
            }
        )
        
        post_event.engagement_score = self.calculate_engagement_score(
            likes=post_event.likes,
            comments=post_event.comments_count,
        )
        
        result.posts.append(post_event)
        
        # Collect comments
        try:
            for comment in post.get_comments():
                comment_event = CommentEvent(
                    platform_comment_id=str(comment.id) if hasattr(comment, 'id') else None,
                    author=comment.owner.username if hasattr(comment, 'owner') else None,
                    created_at=comment.created_at_utc if hasattr(comment, 'created_at_utc') else None,
                    text=comment.text if hasattr(comment, 'text') else '',
                    normalized_text=self.normalize_comment_text(comment.text) if hasattr(comment, 'text') else '',
                    score=comment.likes_count if hasattr(comment, 'likes_count') else 0,
                )
                result.comments.append((post.shortcode, comment_event))
        except Exception:
            # Skip comment errors
            pass


# Allow standalone testing
if __name__ == "__main__":
    collector = InstagramCollector()
    
    if not collector.is_available():
        print("Instagram collector not available. Install: pip install instaloader")
    else:
        print("Collecting from Instagram...")
        result = collector.collect()
        print(f"Collected {len(result.posts)} posts and {len(result.comments)} comments")
        
        if result.errors:
            print(f"Errors: {result.errors}")
        
        for post in result.posts[:3]:
            print(f"\n@{post.author}: {post.text[:80] if post.text else 'No caption'}...")
            print(f"  Likes: {post.likes}")
            print(f"  Hashtags: {post.hashtags}")
