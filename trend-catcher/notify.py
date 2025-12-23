import logging
import requests
import yaml
from pathlib import Path
from typing import Optional

# Configure logging
logger = logging.getLogger("notify")

class Notifier:
    """
    Simple Telegram notifier for Trend Catcher.
    Reads credentials from the main project config.
    """
    def __init__(self):
        self.token = None
        self.chat_id = None
        self.enabled = False
        self._load_config()

    def _load_config(self):
        """Load Telegram settings from ../config/config.yaml"""
        try:
            # Go up one level from trend-catcher/notify.py -> meme-radar/ -> config/config.yaml
            config_path = Path(__file__).parent.parent / "config" / "config.yaml"
            
            if not config_path.exists():
                logger.error(f"Config file not found at {config_path}")
                return

            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
            
            tg_conf = config.get("telegram", {})
            self.token = tg_conf.get("bot_token")
            self.chat_id = tg_conf.get("chat_id")
            self.enabled = tg_conf.get("enabled", False)
            
            if self.enabled and self.token and self.chat_id:
                logger.info("Telegram notification system initialized.")
            else:
                logger.warning("Telegram disabled or missing credentials.")
                
        except Exception as e:
            logger.error(f"Failed to load Telegram config: {e}")

    def send(self, message: str) -> bool:
        """Send a message to the configured Telegram chat."""
        if not self.enabled or not self.token or not self.chat_id:
            logger.debug("Notifications skipped (disabled or invalid config)")
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info("Notification sent successfully.")
                return True
            else:
                logger.error(f"Telegram API Error {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return False

    def notify_trend(self, video_data: dict, velocity: float, acceleration: float = 0.0, trend_type: str = "HOT ENTRY"):
        """
        Format and send a trend alert.
        """
        emoji = "🔥" if trend_type == "HOT ENTRY" else "🚀"
        
        # Format metrics
        vel_str = f"{int(velocity):,}/hr"
        acc_str = f"{int(acceleration):,}/hr²" if acceleration > 0 else "N/A"
        
        stats = video_data.get('stats', {})
        plays = f"{stats.get('playCount', 0):,}"
        likes = f"{stats.get('diggCount', 0):,}"
        shares = f"{stats.get('shareCount', 0):,}"
        
        caption = video_data.get('desc', '') or ''
        # Truncate caption
        if len(caption) > 100:
            caption = caption[:97] + "..."
            
        author = video_data.get('author', 'Unknown')
        link = video_data.get('permalink', '')

        msg = f"""
<b>━━━ {emoji} {trend_type} ━━━</b>

<b>👤 Author:</b> @{author}
<b>⚡ Velocity:</b> <code>{vel_str}</code>
<b>📈 Accel:</b> <code>{acc_str}</code>

<b>📊 Current Stats</b>
👁 Parsed Views: <code>{plays}</code>
❤️ Likes: <code>{likes}</code>
🔄 Shares: <code>{shares}</code>

<b>📝 Caption</b>
<i>{caption}</i>

<a href="{link}">🔗 WATCH VIDEO</a>
"""
        return self.send(msg.strip())
    
    def notify_hashtag_match(self, video_data: dict, matched_hashtags: list[str]):
        """
        Send notification for hashtag-whitelisted content.
        These bypass normal trend detection and are sent for manual review.
        """
        stats = video_data.get('stats', {})
        plays = f"{stats.get('playCount', 0):,}"
        likes = f"{stats.get('diggCount', 0):,}"
        shares = f"{stats.get('shareCount', 0):,}"
        
        caption = video_data.get('desc', '') or ''
        # Truncate caption
        if len(caption) > 150:
            caption = caption[:147] + "..."
            
        author = video_data.get('author', 'Unknown')
        link = video_data.get('permalink', '')
        
        # Format matched hashtags
        hashtag_str = ", ".join([f"#{tag}" for tag in matched_hashtags[:5]])  # Show max 5
        
        msg = f"""
<b>━━━ 🏷️ HASHTAG MATCH ━━━</b>

<b>✅ Matched:</b> <code>{hashtag_str}</code>

<b>👤 Author:</b> @{author}

<b>📊 Stats</b>
👁 Views: <code>{plays}</code>
❤️ Likes: <code>{likes}</code>
🔄 Shares: <code>{shares}</code>

<b>📝 Caption</b>
<i>{caption}</i>

<a href="{link}">🔗 WATCH VIDEO</a>
"""
        return self.send(msg.strip())
    
    def notify_new_video(self, video_data: dict):
        """
        Send notification for new trending video (sorted by engagement).
        """
        stats = video_data.get('stats', {})
        plays = f"{stats.get('playCount', 0):,}"
        likes = f"{stats.get('diggCount', 0):,}"
        shares = f"{stats.get('shareCount', 0):,}"
        comments = f"{stats.get('commentCount', 0):,}"
        
        caption = video_data.get('desc', '') or ''
        # Truncate caption
        if len(caption) > 120:
            caption = caption[:117] + "..."
            
        author = video_data.get('author', 'Unknown')
        link = video_data.get('permalink', '')
        
        msg = f"""
<b>━━━ 🔥 NEW TRENDING VIDEO ━━━</b>

<b>👤 Author:</b> @{author}

<b>📊 Engagement Stats</b>
👁 Views: <code>{plays}</code>
❤️ Likes: <code>{likes}</code>
💬 Comments: <code>{comments}</code>
🔄 Shares: <code>{shares}</code>

<b>📝 Caption</b>
<i>{caption}</i>

<a href="{link}">🔗 WATCH VIDEO</a>
"""
        return self.send(msg.strip())
    
    def _format_number(self, num: int) -> str:
        """Format large numbers with M/K suffixes."""
        if num >= 1_000_000:
            return f"{num / 1_000_000:.1f}M"
        elif num >= 1_000:
            return f"{num / 1_000:.1f}K"
        else:
            return str(num)
    
    def notify_batch_videos(self, videos: list, new_video_ids: set = None) -> bool:
        """
        Send ONE consolidated message with all videos ranked by engagement.
        
        Args:
            videos: List of video data dicts with stats
            new_video_ids: Set of video IDs that are NEW this cycle
        """
        if not videos:
            logger.info("No videos to notify about.")
            return False
        
        if new_video_ids is None:
            new_video_ids = set()
        
        # Import hashtag extraction
        import re
        
        # Build message header
        new_count = len(new_video_ids)
        total_count = len(videos)
        
        if new_count > 0:
            header = f"🔥 <b>TRENDING VIDEOS</b> ({new_count} NEW / {total_count} total)"
        else:
            header = f"📊 <b>TRENDING VIDEOS</b> ({total_count} total)"
        
        lines = [header, "━━━━━━━━━━━━━━━━━━━━━━━━", ""]
        
        # Build video entries
        for i, video in enumerate(videos, 1):
            stats = video.get('stats', {})
            views = self._format_number(stats.get('playCount', 0))
            likes = self._format_number(stats.get('diggCount', 0))
            comments = self._format_number(stats.get('commentCount', 0))
            shares = self._format_number(stats.get('shareCount', 0))
            
            author = video.get('author', 'Unknown')
            link = video.get('permalink', '')
            v_id = video.get('id', '')
            desc = video.get('desc', '') or ''
            
            # Get creation date
            create_time = video.get('create_time')
            if create_time:
                date_str = create_time.strftime("%Y-%m-%d")
            else:
                date_str = "Unknown"
            
            # Extract hashtags from description
            hashtags = re.findall(r'#(\w+)', desc)
            hashtag_str = " ".join([f"#{tag}" for tag in hashtags[:5]]) if hashtags else "No hashtags"
            
            # Truncate description (remove hashtags for cleaner display)
            desc_clean = re.sub(r'#\w+', '', desc).strip()
            if len(desc_clean) > 80:
                desc_clean = desc_clean[:77] + "..."
            
            # Mark NEW videos
            new_badge = "🆕 " if v_id in new_video_ids else ""
            
            # Rank emoji
            if i == 1:
                rank = "🥇"
            elif i == 2:
                rank = "🥈"
            elif i == 3:
                rank = "🥉"
            else:
                rank = f"{i}."
            
            entry = f"""{rank} {new_badge}<b>@{author}</b> <i>({date_str})</i>
   👁 {views} | ❤️ {likes} | 💬 {comments} | 🔄 {shares}
   📝 <i>{desc_clean}</i>
   🏷️ {hashtag_str}
   <a href="{link}">🔗 Watch</a>
"""
            lines.append(entry)
        
        # Footer with timestamp
        from datetime import datetime
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"<i>Scraped: {timestamp}</i>")
        
        message = "\n".join(lines)
        
        # Check Telegram message limit (4096 chars)
        if len(message) > 4000:
            logger.warning(f"Message too long ({len(message)} chars), truncating...")
            # Send what we can
            message = message[:4000] + "\n\n<i>... (truncated)</i>"
        
        return self.send(message)
