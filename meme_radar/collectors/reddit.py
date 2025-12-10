"""
Reddit collector using PRAW (Python Reddit API Wrapper).

Monitors designated meme subreddits for rising posts and captures
post content, engagement metrics, and top comments.
"""

from datetime import datetime
from typing import Optional

from .base import BaseCollector, CollectionResult, CommentEvent, PostEvent


class RedditCollector(BaseCollector):
    """
    Collector for Reddit using PRAW.
    
    Monitors configured subreddits, polling 'rising' and 'new' feeds
    to catch early memes before they go viral.
    """
    
    PLATFORM_NAME = "reddit"
    
    def __init__(self):
        super().__init__()
        self._reddit = None
    
    @property
    def reddit(self):
        """Lazy-load the PRAW Reddit instance."""
        if self._reddit is None:
            import praw
            
            client_id = self.config.get("reddit", "client_id")
            client_secret = self.config.get("reddit", "client_secret")
            user_agent = self.config.get("reddit", "user_agent", default="MemeRadar/1.0")
            
            if not client_id or not client_secret:
                raise ValueError(
                    "Reddit credentials not configured. "
                    "Set reddit.client_id and reddit.client_secret in config.yaml "
                    "or REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET environment variables."
                )
            
            self._reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
            )
        
        return self._reddit
    
    def is_available(self) -> bool:
        """Check if PRAW is installed and credentials are configured."""
        try:
            import praw
            
            client_id = self.config.get("reddit", "client_id")
            client_secret = self.config.get("reddit", "client_secret")
            
            return bool(client_id and client_secret)
        except ImportError:
            return False
    
    def collect(self) -> CollectionResult:
        """
        Collect posts from configured subreddits.
        
        Monitors both 'rising' and 'new' feeds to catch early trends.
        """
        result = CollectionResult(platform=self.PLATFORM_NAME)
        
        if not self.config.get("reddit", "enabled", default=True):
            result.errors.append("Reddit collector is disabled in config")
            return result
        
        subreddits = self.config.get("reddit", "subreddits", default=[])
        max_posts = self.config.get("reddit", "max_posts_per_subreddit", default=50)
        comments_per_post = self.config.get("reddit", "comments_per_post", default=10)
        
        try:
            for subreddit_name in subreddits:
                self._collect_subreddit(
                    subreddit_name,
                    max_posts,
                    comments_per_post,
                    result,
                )
        except Exception as e:
            result.errors.append(f"Error collecting from Reddit: {str(e)}")
        
        result.completed_at = datetime.utcnow()
        return result
    
    def _collect_subreddit(
        self,
        subreddit_name: str,
        max_posts: int,
        comments_per_post: int,
        result: CollectionResult,
    ) -> None:
        """Collect posts from a single subreddit."""
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            
            # Collect from both rising and new for early detection
            seen_ids = set()
            
            for submission in subreddit.rising(limit=max_posts // 2):
                if submission.id not in seen_ids:
                    self._process_submission(submission, comments_per_post, result)
                    seen_ids.add(submission.id)
            
            for submission in subreddit.new(limit=max_posts // 2):
                if submission.id not in seen_ids:
                    self._process_submission(submission, comments_per_post, result)
                    seen_ids.add(submission.id)
                    
        except Exception as e:
            result.errors.append(f"Error in r/{subreddit_name}: {str(e)}")
    
    def _process_submission(
        self,
        submission,
        comments_per_post: int,
        result: CollectionResult,
    ) -> None:
        """Process a single Reddit submission."""
        # Build post event
        post = PostEvent(
            platform=self.PLATFORM_NAME,
            platform_post_id=submission.id,
            author=str(submission.author) if submission.author else "[deleted]",
            created_at=datetime.utcfromtimestamp(submission.created_utc),
            text=f"{submission.title}\n\n{submission.selftext}" if submission.selftext else submission.title,
            permalink=f"https://reddit.com{submission.permalink}",
            likes=submission.score,
            shares=0,  # Reddit doesn't expose share count
            comments_count=submission.num_comments,
            hashtags=self.extract_hashtags(f"{submission.title} {submission.selftext}"),
            upvote_ratio=submission.upvote_ratio,
            subreddit=submission.subreddit.display_name,
            raw_metadata={
                "is_self": submission.is_self,
                "link_flair_text": submission.link_flair_text,
                "over_18": submission.over_18,
            }
        )
        
        # Calculate engagement score
        post.engagement_score = self.calculate_engagement_score(
            likes=submission.score,
            comments=submission.num_comments,
        )
        
        # Extract media URLs
        if hasattr(submission, 'url') and submission.url:
            url = submission.url
            if any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                post.media_urls.append((url, 'image'))
            elif any(ext in url.lower() for ext in ['.mp4', '.webm', '.gifv']):
                post.media_urls.append((url, 'video'))
            elif 'i.redd.it' in url:
                post.media_urls.append((url, 'image'))
            elif 'v.redd.it' in url:
                post.media_urls.append((url, 'video'))
        
        # Check for gallery posts
        if hasattr(submission, 'is_gallery') and submission.is_gallery:
            if hasattr(submission, 'media_metadata') and submission.media_metadata:
                for media_id, media_info in submission.media_metadata.items():
                    if 's' in media_info and 'u' in media_info['s']:
                        media_url = media_info['s']['u'].replace('&amp;', '&')
                        post.media_urls.append((media_url, 'image'))
        
        result.posts.append(post)
        
        # Collect top comments
        if comments_per_post > 0:
            try:
                submission.comment_sort = 'top'
                submission.comments.replace_more(limit=0)  # Don't load "more comments"
                
                for comment in submission.comments[:comments_per_post]:
                    if hasattr(comment, 'body') and comment.body:
                        comment_event = CommentEvent(
                            platform_comment_id=comment.id,
                            author=str(comment.author) if comment.author else "[deleted]",
                            created_at=datetime.utcfromtimestamp(comment.created_utc),
                            text=comment.body,
                            normalized_text=self.normalize_comment_text(comment.body),
                            score=comment.score,
                            raw_metadata={
                                "is_submitter": comment.is_submitter,
                                "stickied": comment.stickied,
                            }
                        )
                        result.comments.append((submission.id, comment_event))
            except Exception:
                # Skip comment errors, don't fail the whole post
                pass


# Allow standalone testing
if __name__ == "__main__":
    collector = RedditCollector()
    
    if not collector.is_available():
        print("Reddit collector not available. Check credentials.")
    else:
        print("Collecting from Reddit...")
        result = collector.collect()
        print(f"Collected {len(result.posts)} posts and {len(result.comments)} comments")
        
        if result.errors:
            print(f"Errors: {result.errors}")
        
        # Show sample
        for post in result.posts[:3]:
            print(f"\n[r/{post.subreddit}] {post.text[:100]}...")
            print(f"  Score: {post.likes}, Comments: {post.comments_count}")
            print(f"  Hashtags: {post.hashtags}")
