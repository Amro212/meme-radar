"""
Telegram notification module for Meme Radar.

Sends comprehensive trend alerts to Telegram with actionable information.
"""

import logging
import requests
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Sends formatted alerts to Telegram.
    
    Provides comprehensive trend information for quick action.
    """
    
    API_BASE = "https://api.telegram.org/bot{token}"
    
    def __init__(self, config):
        self.config = config
        self._token = config.get("telegram", "bot_token")
        self._chat_id = config.get("telegram", "chat_id")
        self._enabled = config.get("telegram", "enabled", default=False)
        self._last_sent = {}
    
    def is_available(self) -> bool:
        """Check if Telegram is configured."""
        return self._enabled and bool(self._token) and bool(self._chat_id)
    
    def _send_message(self, text: str, parse_mode: str = "HTML", disable_preview: bool = False) -> bool:
        """Send message to Telegram."""
        if not self.is_available():
            return False
        
        try:
            url = f"{self.API_BASE.format(token=self._token)}/sendMessage"
            payload = {
                "chat_id": self._chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": disable_preview,
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                return True
            else:
                logger.error(f"Telegram API error: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════════
    # HOT VIDEO ALERTS - Main detection notification
    # ═══════════════════════════════════════════════════════════════
    
    def notify_hot_video(
        self,
        username: str,
        likes: int,
        shares: int,
        comments: int,
        views: int,
        spike_factor: float,
        meme_score: float,
        video_url: Optional[str] = None,
        caption: Optional[str] = None,
        hashtags: Optional[List[str]] = None,
        is_discourse: bool = False,
        likes_to_views: float = 0.0,
        shares_to_likes: float = 0.0,
    ) -> bool:
        """
        Send a hot video detection alert with full context.
        """
        key = f"video:{video_url}"
        if self._is_recently_sent(key, minutes=60):
            return False
        
        # Determine alert type and emoji
        if is_discourse:
            header = "💬 DISCOURSE MEME DETECTED"
            signal_desc = "High comments + low L/V ratio = viral debate potential"
        elif spike_factor >= 20:
            header = "🚀 MEGA VIRAL SPIKE"
            signal_desc = f"{spike_factor:.0f}x above creator average"
        elif shares_to_likes >= 0.3:
            header = "📤 HIGH SHARE RATIO"
            signal_desc = "Strong dark social spreading signal"
        elif meme_score >= 0.7:
            header = "🔥 HOT MEME SEED"
            signal_desc = f"Meme potential score: {meme_score:.0%}"
        else:
            header = "📈 TRENDING VIDEO"
            signal_desc = f"Spike: {spike_factor:.1f}x average"
        
        # Format numbers
        likes_str = self._format_number(likes)
        shares_str = self._format_number(shares)
        comments_str = self._format_number(comments)
        views_str = self._format_number(views) if views > 0 else "N/A"
        
        # Build message
        message = f"""
<b>━━━ {header} ━━━</b>

👤 <b>Creator:</b> @{username}
📊 <b>Signal:</b> {signal_desc}

<b>┌ ENGAGEMENT</b>
│ ❤️ Likes: <code>{likes_str}</code>
│ 🔄 Shares: <code>{shares_str}</code>
│ 💬 Comments: <code>{comments_str}</code>
│ 👁 Views: <code>{views_str}</code>
<b>└</b>

<b>┌ RATIOS</b>
│ L/V: <code>{likes_to_views:.2%}</code> {"⚠️ Low" if likes_to_views < 0.02 else ""}
│ S/L: <code>{shares_to_likes:.2%}</code> {"🔥 High" if shares_to_likes >= 0.1 else ""}
<b>└</b>

<b>🎯 Meme Score:</b> <code>{meme_score:.0%}</code>
"""
        
        # Add caption preview
        if caption:
            preview = caption[:100] + "..." if len(caption) > 100 else caption
            message += f"\n<b>📝 Caption:</b>\n<i>{preview}</i>\n"
        
        # Add hashtags
        if hashtags and len(hashtags) > 0:
            tags = " ".join([f"#{h}" for h in hashtags[:5]])
            message += f"\n<b>🏷 Tags:</b> {tags}\n"
        
        # Add link
        if video_url:
            message += f"\n🔗 <a href=\"{video_url}\">WATCH NOW</a>"
        
        # Add timestamp
        now = datetime.now().strftime("%H:%M EST")
        message += f"\n\n<i>Detected at {now}</i>"
        
        if self._send_message(message.strip(), disable_preview=False):
            self._mark_sent(key)
            return True
        return False
    
    # ═══════════════════════════════════════════════════════════════
    # TREND ALERTS - Hashtag/phrase detection
    # ═══════════════════════════════════════════════════════════════
    
    def notify_trend(
        self,
        term: str,
        acceleration: float,
        frequency: int,
        platform: str,
        zscore: float = 0.0,
        example_url: Optional[str] = None,
    ) -> bool:
        """Send a trend detection alert."""
        key = f"trend:{term}:{platform}"
        if self._is_recently_sent(key, minutes=30):
            return False
        
        # Determine urgency
        if acceleration >= 10:
            emoji = "🚨"
            urgency = "EXPLOSIVE"
        elif acceleration >= 5:
            emoji = "🔥"
            urgency = "HOT"
        elif zscore >= 3:
            emoji = "📈"
            urgency = "RISING"
        else:
            emoji = "👀"
            urgency = "EMERGING"
        
        message = f"""
<b>━━━ {emoji} {urgency} TREND ━━━</b>

<b>🏷 Term:</b> <code>{term}</code>
<b>📱 Platform:</b> {platform.upper()}

<b>┌ METRICS</b>
│ ⚡ Acceleration: <code>{acceleration:.1f}x</code>
│ 📊 Frequency: <code>{frequency}</code>
│ 📈 Z-Score: <code>{zscore:.2f}</code>
<b>└</b>
"""
        
        if example_url:
            message += f"\n🔗 <a href=\"{example_url}\">View Example</a>"
        
        now = datetime.now().strftime("%H:%M EST")
        message += f"\n\n<i>Detected at {now}</i>"
        
        if self._send_message(message.strip()):
            self._mark_sent(key)
            return True
        return False
    
    # ═══════════════════════════════════════════════════════════════
    # WATCHLIST ALERTS - Creator added to monitoring
    # ═══════════════════════════════════════════════════════════════
    
    def notify_watchlist(
        self,
        username: str,
        reason: str,
        avg_score: float,
        recent_hits: int,
        profile_url: Optional[str] = None,
    ) -> bool:
        """Notify when a creator is added to watchlist."""
        key = f"watchlist:{username}"
        if self._is_recently_sent(key, minutes=120):
            return False
        
        message = f"""
<b>━━━ 🎯 NEW WATCHLIST CREATOR ━━━</b>

<b>👤 Creator:</b> @{username}
<b>📝 Reason:</b> {reason}

<b>┌ STATS</b>
│ 🎯 Avg Score: <code>{avg_score:.0%}</code>
│ 🔥 Recent Hits: <code>{recent_hits}</code>
<b>└</b>
"""
        
        if profile_url:
            message += f"\n🔗 <a href=\"{profile_url}\">View Profile</a>"
        
        if self._send_message(message.strip()):
            self._mark_sent(key)
            return True
        return False
    
    # ═══════════════════════════════════════════════════════════════
    # PIPELINE SUMMARY - Run completion report
    # ═══════════════════════════════════════════════════════════════
    
    def notify_pipeline_summary(
        self,
        posts_collected: int,
        hot_videos: int,
        trends_detected: int,
        watchlist_additions: int,
        errors: int = 0,
        duration_seconds: float = 0,
    ) -> bool:
        """Send a pipeline run summary."""
        # Only send if there's something notable
        if hot_videos == 0 and trends_detected == 0 and watchlist_additions == 0:
            return False
        
        now = datetime.now().strftime("%H:%M EST")
        
        # Status emoji
        if hot_videos >= 3:
            status = "🔥🔥🔥"
        elif hot_videos >= 1:
            status = "🔥"
        else:
            status = "📊"
        
        message = f"""
<b>━━━ {status} RADAR SCAN COMPLETE ━━━</b>

<b>⏰ Time:</b> {now}
<b>⏱ Duration:</b> {duration_seconds:.0f}s

<b>┌ RESULTS</b>
│ 📥 Posts: <code>{posts_collected}</code>
│ 🔥 Hot Videos: <code>{hot_videos}</code>
│ 📈 Trends: <code>{trends_detected}</code>
│ 🎯 Watchlist: <code>+{watchlist_additions}</code>
<b>└</b>
"""
        
        if errors > 0:
            message += f"\n⚠️ <i>{errors} errors occurred</i>"
        
        return self._send_message(message.strip(), disable_preview=True)
    
    # ═══════════════════════════════════════════════════════════════
    # STARTUP / TEST
    # ═══════════════════════════════════════════════════════════════
    
    def send_startup_message(self) -> bool:
        """Send startup notification."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M EST")
        
        message = f"""
<b>━━━ 🚀 MEME RADAR ONLINE ━━━</b>

<b>⏰ Started:</b> {now}

<b>Monitoring:</b>
• TikTok users and hashtags
• Viral spike detection
• Meme seed scoring
• Discourse signals

<i>You'll receive alerts when hot content is detected.</i>
"""
        return self._send_message(message.strip(), disable_preview=True)
    
    def send_test_message(self) -> bool:
        """Send a test message to verify configuration."""
        message = """
<b>━━━ ✅ MEME RADAR CONNECTED ━━━</b>

Your Telegram notifications are working.

<b>You'll receive alerts when:</b>
• 🔥 Hot videos are detected
• 📈 New trends emerge
• 🎯 Creators hit watchlist
• 📊 Pipeline runs complete

<i>Run the scheduler to start monitoring!</i>
"""
        return self._send_message(message.strip(), disable_preview=True)
    
    # ═══════════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════════
    
    def _format_number(self, num: int) -> str:
        """Format large numbers with K/M suffixes."""
        if num >= 1_000_000:
            return f"{num / 1_000_000:.1f}M"
        elif num >= 1_000:
            return f"{num / 1_000:.1f}K"
        return str(num)
    
    def _is_recently_sent(self, key: str, minutes: int = 30) -> bool:
        """Check if this notification was sent recently."""
        if key not in self._last_sent:
            return False
        
        from datetime import timedelta
        age = datetime.utcnow() - self._last_sent[key]
        return age < timedelta(minutes=minutes)
    
    def _mark_sent(self, key: str) -> None:
        """Mark a notification as sent."""
        self._last_sent[key] = datetime.utcnow()


def get_telegram_notifier(config) -> TelegramNotifier:
    """Get a configured Telegram notifier instance."""
    return TelegramNotifier(config)
