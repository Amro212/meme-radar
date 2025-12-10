"""
Twitter/X collector using snscrape.

Fetches recent high-engagement tweets to approximate trending content.
"""

from datetime import datetime, timedelta
from typing import Optional

from .base import BaseCollector, CollectionResult, PostEvent


class TwitterCollector(BaseCollector):
    """
    Collector for Twitter/X using snscrape.
    
    Note: snscrape may have intermittent issues due to Twitter API changes.
    The collector handles errors gracefully and returns partial results.
    """
    
    PLATFORM_NAME = "twitter"
    
    def __init__(self):
        super().__init__()
        self._snscrape_available = None
    
    def is_available(self) -> bool:
        """Check if snscrape is installed."""
        if self._snscrape_available is None:
            try:
                import snscrape.modules.twitter as sntwitter
                self._snscrape_available = True
            except ImportError:
                self._snscrape_available = False
        return self._snscrape_available
    
    def collect(self) -> CollectionResult:
        """
        Collect tweets using snscrape.
        
        Searches for tweets matching configured queries with minimum engagement.
        """
        result = CollectionResult(platform=self.PLATFORM_NAME)
        
        if not self.config.get("twitter", "enabled", default=True):
            result.errors.append("Twitter collector is disabled in config")
            return result
        
        if not self.is_available():
            result.errors.append(
                "snscrape not installed. Install with: pip install snscrape"
            )
            return result
        
        import snscrape.modules.twitter as sntwitter
        
        queries = self.config.get("twitter", "queries", default=["meme"])
        min_likes = self.config.get("twitter", "min_likes", default=50)
        min_retweets = self.config.get("twitter", "min_retweets", default=10)
        max_tweets = self.config.get("twitter", "max_tweets_per_query", default=100)
        
        # Calculate time window (default: last 60 minutes)
        time_window = self.config.get("analysis", "time_window_minutes", default=60)
        since_time = datetime.utcnow() - timedelta(minutes=time_window)
        
        for query in queries:
            try:
                self._collect_query(
                    query,
                    since_time,
                    min_likes,
                    min_retweets,
                    max_tweets,
                    result,
                )
            except Exception as e:
                result.errors.append(f"Error searching '{query}': {str(e)}")
        
        result.completed_at = datetime.utcnow()
        return result
    
    def _collect_query(
        self,
        query: str,
        since_time: datetime,
        min_likes: int,
        min_retweets: int,
        max_tweets: int,
        result: CollectionResult,
    ) -> None:
        """Collect tweets for a single search query."""
        import snscrape.modules.twitter as sntwitter
        
        # Build search query with engagement filters
        search_query = f"{query} min_faves:{min_likes} min_retweets:{min_retweets}"
        
        try:
            scraper = sntwitter.TwitterSearchScraper(search_query)
            
            count = 0
            for tweet in scraper.get_items():
                if count >= max_tweets:
                    break
                
                # Skip tweets older than our time window
                if tweet.date.replace(tzinfo=None) < since_time:
                    continue
                
                post = self._create_post_event(tweet)
                result.posts.append(post)
                count += 1
                
        except Exception as e:
            result.errors.append(f"snscrape error for '{query}': {str(e)}")
    
    def _create_post_event(self, tweet) -> PostEvent:
        """Convert a snscrape tweet object to PostEvent."""
        # Extract text, handling quoted tweets
        text = tweet.rawContent if hasattr(tweet, 'rawContent') else tweet.content
        
        # Extract hashtags from the tweet
        hashtags = self.extract_hashtags(text)
        if hasattr(tweet, 'hashtags') and tweet.hashtags:
            hashtags = list(set(hashtags + [tag.lower() for tag in tweet.hashtags]))
        
        # Extract media URLs
        media_urls = []
        if hasattr(tweet, 'media') and tweet.media:
            for media in tweet.media:
                if hasattr(media, 'fullUrl'):
                    media_type = 'video' if hasattr(media, 'duration') else 'image'
                    media_urls.append((media.fullUrl, media_type))
                elif hasattr(media, 'previewUrl'):
                    media_urls.append((media.previewUrl, 'image'))
        
        post = PostEvent(
            platform=self.PLATFORM_NAME,
            platform_post_id=str(tweet.id),
            author=tweet.user.username if hasattr(tweet, 'user') and tweet.user else None,
            created_at=tweet.date.replace(tzinfo=None) if tweet.date else None,
            text=text,
            permalink=tweet.url if hasattr(tweet, 'url') else None,
            likes=tweet.likeCount if hasattr(tweet, 'likeCount') else 0,
            shares=tweet.retweetCount if hasattr(tweet, 'retweetCount') else 0,
            comments_count=tweet.replyCount if hasattr(tweet, 'replyCount') else 0,
            hashtags=hashtags,
            media_urls=media_urls,
            raw_metadata={
                "quote_count": tweet.quoteCount if hasattr(tweet, 'quoteCount') else 0,
                "view_count": tweet.viewCount if hasattr(tweet, 'viewCount') else None,
                "is_retweet": hasattr(tweet, 'retweetedTweet') and tweet.retweetedTweet is not None,
            }
        )
        
        # Calculate engagement score
        views = tweet.viewCount if hasattr(tweet, 'viewCount') and tweet.viewCount else 0
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
        print("Twitter collector not available. Install snscrape: pip install snscrape")
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
