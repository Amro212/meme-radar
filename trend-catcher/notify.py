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
