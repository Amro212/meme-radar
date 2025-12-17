"""
Telegram notification module for Meme Radar.

Uses database-backed tracking to prevent duplicate notifications across restarts.
"""

import logging
import requests
from datetime import datetime, timedelta
from typing import Optional, List

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Sends formatted alerts to Telegram.
    
    Uses database to track notifications and prevent spam.
    """
    
    API_BASE = "https://api.telegram.org/bot{token}"
    
    def __init__(self, config):
        self.config = config
        self._token = config.get("telegram", "bot_token")
        self._chat_id = config.get("telegram", "chat_id")
        self._enabled = config.get("telegram", "enabled", default=False)
        
        # Load noise filter
        self._evergreen_hashtags = set(
            h.lower() for h in config.get("noise", "evergreen_hashtags", default=[])
        )
    
    def is_available(self) -> bool:
        """Check if Telegram is configured."""
        return self._enabled and bool(self._token) and bool(self._chat_id)
    
    def _is_noise_term(self, term: str) -> bool:
        """Check if term should be filtered as noise."""
        return term.lower() in self._evergreen_hashtags
    
    def _was_recently_notified(self, item_type: str, item_key: str, cooldown_minutes: int = 60) -> bool:
        """Check database if this item was recently notified."""
        try:
            from .database import get_session
            from .models import NotifiedItem
            
            with get_session() as session:
                cutoff = datetime.utcnow() - timedelta(minutes=cooldown_minutes)
                existing = session.query(NotifiedItem).filter(
                    NotifiedItem.item_type == item_type,
                    NotifiedItem.item_key == item_key,
                    NotifiedItem.notified_at >= cutoff
                ).first()
                return existing is not None
        except Exception as e:
            logger.warning(f"Could not check notification history: {e}")
            return False
    
    def _record_notification(self, item_type: str, item_key: str, cooldown_minutes: int = 60) -> None:
        """Record that we notified on this item."""
        try:
            from .database import get_session
            from .models import NotifiedItem
            
            with get_session() as session:
                # Upsert - update if exists, insert if not
                existing = session.query(NotifiedItem).filter(
                    NotifiedItem.item_type == item_type,
                    NotifiedItem.item_key == item_key
                ).first()
                
                if existing:
                    existing.notified_at = datetime.utcnow()
                    existing.cooldown_minutes = cooldown_minutes
                else:
                    new_item = NotifiedItem(
                        item_type=item_type,
                        item_key=item_key,
                        cooldown_minutes=cooldown_minutes
                    )
                    session.add(new_item)
                session.commit()
        except Exception as e:
            logger.warning(f"Could not record notification: {e}")
    
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
    # HOT VIDEO ALERTS
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
        """Send a hot video detection alert."""
        # Use video URL as unique key
        item_key = video_url or f"{username}:{likes}"
        
        # Check if already notified (60 minute cooldown)
        if self._was_recently_notified("video", item_key, cooldown_minutes=60):
            return False
        
        # 1. Identify all detection signals
        signals = []
        
        # Share Ratio (The "Dark Social" Indicator)
        if shares_to_likes >= 0.1:
            intensity = "EXTREME" if shares_to_likes >= 0.3 else "HIGH"
            signals.append(f"🔄 <b>Dark Social ({intensity}):</b> {shares_to_likes:.1%} share ratio indicates viral spread via DMs.")
            
        # Discourse (The "Controversy" Indicator)
        if is_discourse:
            signals.append("💬 <b>Controversy Signal:</b> High comment count relative to views/likes indicates debate or confusion.")
            
        # Spike Factor (The "Outlier" Indicator)
        if spike_factor >= 3.0:
            signals.append(f"🚀 <b>Statistical Outlier:</b> Performing {spike_factor:.1f}x better than this creator's average.")
            
        # Meme Score (Overall Quality)
        if meme_score >= 0.7:
             signals.append(f"🔥 <b>High Potential:</b> Overall meme-seed score of {meme_score:.0%} is exceptional.")

        # Determine main header based on strongest signal
        if meme_score >= 0.8:
            header = "🔥 DIAMOND MEME SEED"
        elif is_discourse:
            header = "💬 DISCOURSE/DRAMA DETECTED"
        elif shares_to_likes >= 0.2:
            header = "� VIRAL SHARE SPIKE"
        else:
            header = "🚀 RISING HIT DETECTED"
        
        # Format numbers
        likes_str = self._format_number(likes)
        shares_str = self._format_number(shares)
        comments_str = self._format_number(comments)
        views_str = self._format_number(views) if views > 0 else "N/A"
        
        # Build Message
        message = f"""
<b>━━━ {header} ━━━</b>

👤 <b>Creator:</b> @{username}
🏆 <b>Score:</b> <code>{meme_score:.0%}</code>

<b>🔍 DETECTION CONTEXT</b>
"""
        # Add bullet points for signals
        for sig in signals:
            message += f"• {sig}\n"
            
        message += f"""
<b>📊 METRICS</b>
┌ ❤️ Likes: <code>{likes_str}</code>
│ 🔄 Shares: <code>{shares_str}</code> (S/L: {shares_to_likes:.1%})
│ 💬 Comments: <code>{comments_str}</code>
└ 👁 Views: <code>{views_str}</code>
"""
        
        # Add caption preview
        if caption:
            # Clean up caption (remove excessive newlines)
            clean_caption = caption.replace('\n', ' ').strip()
            preview = clean_caption[:100] + "..." if len(clean_caption) > 100 else clean_caption
            message += f"\n<b>📝 Caption:</b>\n<i>{preview}</i>\n"
        
        if video_url:
            message += f"\n🔗 <a href=\"{video_url}\">WATCH ON TIKTOK</a>"
        
        now = datetime.now().strftime("%H:%M EST")
        message += f"\n\n<i>Detected at {now}</i>"
        
        if self._send_message(message.strip(), disable_preview=False):
            self._record_notification("video", item_key, cooldown_minutes=60)
            return True
        return False
    
    # ═══════════════════════════════════════════════════════════════
    # TREND ALERTS
    # ═══════════════════════════════════════════════════════════════
    
    def notify_trend(
        self,
        term: str,
        acceleration: float,
        frequency: int,
        platform: str,
        zscore: float = 0.0,
        example_urls: Optional[List[str]] = None,
        unique_users: int = 0,
    ) -> bool:
        """Send a trend detection alert."""
        # Filter noise terms
        if self._is_noise_term(term):
            return False
        
        item_key = f"{term.lower()}:{platform}"
        
        # Longer cooldown for trends (2 hours)
        if self._was_recently_notified("trend", item_key, cooldown_minutes=120):
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
        
        # Build Context items dynamically (prevents empty bullets)
        context_items = []
        if acceleration >= 2:
            context_items.append(f"Usage spiked <b>{acceleration:.1f}x</b> above baseline.")
        
        if unique_users > 1:
            context_items.append(f"Discussed by <b>{unique_users}</b> unique accounts.")
        elif unique_users == 1:
             context_items.append("Driven by a single active account (check for spam).")
            
        message = f"""
<b>━━━ {emoji} {urgency} TREND ━━━</b>

<b>🏷 Term:</b> <code>{term}</code>
<b>📱 Platform:</b> {platform.upper()}

<b>┌ STATS</b>
│ ⚡ Acceleration: <code>{acceleration:.1f}x</code>
│ 📈 Z-Score: <code>{zscore:.2f}</code>
│ 🔢 Post Count: <code>{frequency}</code>
<b>└</b>
"""

        # Add Context Section
        if context_items:
            message += "\n<b>🔍 CONTEXT</b>\n"
            for item in context_items:
                message += f"• {item}\n"
        
        # Add Examples Section
        if example_urls and len(example_urls) > 0:
            message += "\n<b>🔗 EXAMPLES</b>\n"
            # Show up to 3 links
            for i, url in enumerate(example_urls[:3], 1):
                message += f"• <a href=\"{url}\">Post {i}</a>\n"
        
        now = datetime.now().strftime("%H:%M EST")
        message += f"\n<i>Detected at {now}</i>"
        
        if self._send_message(message.strip()):
            self._record_notification("trend", item_key, cooldown_minutes=120)
            return True
        return False
    
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
• Multi-user trend validation

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
• 📈 Cross-user trends emerge

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


def get_telegram_notifier(config) -> TelegramNotifier:
    """Get a configured Telegram notifier instance."""
    return TelegramNotifier(config)
