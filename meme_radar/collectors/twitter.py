"""
Twitter/X collector using Twikit.

Fetches recent high-engagement tweets using Twikit library.
"""

from datetime import datetime, timedelta
from typing import Optional
import asyncio

from .base import BaseCollector, CollectionResult, PostEvent


class TwitterCollector(BaseCollector):
    """
    Collector for Twitter/X using Twikit.
    
    Uses Twikit to authenticate and search for tweets.
    """
    
    PLATFORM_NAME = "twitter"
    
    def __init__(self):
        super().__init__()
        self._twikit_available = None
        self._client = None
    
    def is_available(self) -> bool:
        """Check if twikit is installed."""
        if self._twikit_available is None:
            try:
                from twikit import Client
                self._twikit_available = True
            except ImportError:
                self._twikit_available = False
        return self._twikit_available
    
    def collect(self) -> CollectionResult:
        """
        Collect tweets using Twikit.
        
        Searches for tweets matching configured queries with minimum engagement.
        """
        result = CollectionResult(platform=self.PLATFORM_NAME)
        
        if not self.config.get("twitter", "enabled", default=True):
            result.errors.append("Twitter collector is disabled in config")
            return result
        
        if not self.is_available():
            result.errors.append(
                "twikit not installed. Install with: pip install twikit"
            )
            return result
        
        # Run async collection
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._collect_async(result))
            finally:
                loop.close()
        except Exception as e:
            result.errors.append(f"Twitter collection error: {str(e)}")
        
        result.completed_at = datetime.utcnow()
        return result
    
    async def _collect_async(self, result: CollectionResult) -> None:
        """Async collection of tweets."""
        from twikit import Client
        
        # Get credentials
        username = self.config.get("twitter", "username")
        password = self.config.get("twitter", "password")
        
        if not username or not password:
            result.errors.append("Twitter username/password not configured")
            return
        
        queries = self.config.get("twitter", "queries", default=["meme"])
        min_likes = self.config.get("twitter", "min_likes", default=50)
        min_retweets = self.config.get("twitter", "min_retweets", default=10)
        max_tweets = self.config.get("twitter", "max_tweets_per_query", default=100)
        
        try:
            # Initialize client
            client = Client('en-US')
            
            # Try to load cookies first
            import os
            cookie_file = '.twikit_cookies.json'
            
            if os.path.exists(cookie_file):
                print(f"[Twitter] Loading saved session...")
                client.load_cookies(cookie_file)
            else:
                print(f"[Twitter] Logging in as {username}...")
                await client.login(
                    auth_info_1=username,
                    password=password
                )
                client.save_cookies(cookie_file)
                print(f"[Twitter] Successfully logged in!")
            
            # Search for each query
            for query in queries:
                try:
                    print(f"[Twitter] Searching for '{query}'...")
                    tweets = await client.search_tweet(query, 'Latest', count=max_tweets)
                    
                    for tweet in tweets:
                        # Filter by engagement
                        if tweet.favorite_count < min_likes or tweet.retweet_count < min_retweets:
                            continue
                        
                        post = self._create_post_event(tweet)
                        result.posts.append(post)
                        
                except Exception as e:
                    result.errors.append(f"Error searching '{query}': {str(e)}")
                    
        except Exception as e:
            result.errors.append(f"Twitter login/search error: {str(e)}")
    
    def _create_post_event(self, tweet) -> PostEvent:
        """Convert a Twikit tweet object to PostEvent."""
        # Extract text
        text = tweet.full_text if hasattr(tweet, 'full_text') else tweet.text
        
        # Extract hashtags
        hashtags = self.extract_hashtags(text)
        
        # Extract media URLs
        media_urls = []
        if hasattr(tweet, 'media') and tweet.media:
            for media in tweet.media:
                if hasattr(media, 'media_url_https'):
                    media_type = media.type if hasattr(media, 'type') else 'image'
                    media_urls.append((media.media_url_https, media_type))
        
        # Build permalink
        username = tweet.user.screen_name if hasattr(tweet, 'user') else 'unknown'
        permalink = f"https://twitter.com/{username}/status/{tweet.id}"
        
        post = PostEvent(
            platform=self.PLATFORM_NAME,
            platform_post_id=str(tweet.id),
            author=username,
            created_at=tweet.created_at if hasattr(tweet, 'created_at') else None,
            text=text,
            permalink=permalink,
            likes=tweet.favorite_count if hasattr(tweet, 'favorite_count') else 0,
            shares=tweet.retweet_count if hasattr(tweet, 'retweet_count') else 0,
            comments_count=tweet.reply_count if hasattr(tweet, 'reply_count') else 0,
            hashtags=hashtags,
            media_urls=media_urls,
            raw_metadata={
                "quote_count": tweet.quote_count if hasattr(tweet, 'quote_count') else 0,
                "view_count": tweet.view_count if hasattr(tweet, 'view_count') else None,
                "is_retweet": hasattr(tweet, 'retweeted_status'),
            }
        )
        
        # Calculate engagement score
        views = tweet.view_count if hasattr(tweet, 'view_count') and tweet.view_count else 0
        post.engagement_score = self.calculate_engagement_score(
            likes=post.likes,
            shares=post.shares,
            comments=post.comments_count,
            views=views,
        )
        
        return post


# Allow standalone testing
if __name__ == "__main__":
    collector = TwitterCollector()
    
    if not collector.is_available():
        print("Twitter collector not available. Install twikit: pip install twikit")
    else:
        print("Collecting from Twitter...")
        result = collector.collect()
        print(f"Collected {len(result.posts)} tweets")
        
        if result.errors:
            print(f"Errors: {result.errors}")
        
        for post in result.posts[:5]:
            print(f"\n@{post.author}: {post.text[:80]}...")
            print(f"  Likes: {post.likes}, Retweets: {post.shares}")
            print(f"  Hashtags: {post.hashtags}")
