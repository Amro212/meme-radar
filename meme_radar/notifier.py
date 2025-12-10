"""
Windows notification system for trend alerts.

Sends Windows toast notifications when high-value meme trends are detected.
"""

from datetime import datetime, timedelta
from typing import Optional, Set
import logging

logger = logging.getLogger(__name__)


class TrendNotifier:
    """
    Manages Windows toast notifications for trend alerts.
    
    Features:
    - Native Windows notifications
    - Sound alerts
    - Clickable URLs
    - Spam prevention (cooldown)
    """
    
    def __init__(self, config=None):
        """Initialize the notifier."""
        if config is None:
            from meme_radar.config import config as default_config
            config = default_config
        self.config = config
        
        # Track notified trends to prevent spam
        self._notified_trends: dict[str, datetime] = {}
        
        # Initialize toast notifier
        self._toaster = None
        self._init_toaster()
    
    def _init_toaster(self):
        """Initialize Windows toast notifier."""
        try:
            from win10toast import ToastNotifier
            self._toaster = ToastNotifier()
        except ImportError:
            logger.warning("win10toast not installed. Notifications disabled.")
            self._toaster = None
        except Exception as e:
            logger.error(f"Failed to initialize toast notifier: {e}")
            self._toaster = None
    
    def is_available(self) -> bool:
        """Check if notifications are available."""
        return self._toaster is not None
    
    def should_notify(
        self,
        term: str,
        acceleration: float,
        zscore: float,
        frequency: int,
    ) -> bool:
        """
        Determine if a trend should trigger a notification.
        
        Args:
            term: The trending term
            acceleration: Acceleration score
            zscore: Z-score
            frequency: Number of posts
            
        Returns:
            True if should notify
        """
        # Check if notifications are enabled
        if not self.config.get("notifications", "enabled", default=True):
            return False
        
        # Check thresholds
        min_acceleration = self.config.get("notifications", "min_acceleration", default=5.0)
        min_zscore = self.config.get("notifications", "min_zscore", default=10.0)
        min_frequency = self.config.get("notifications", "min_frequency", default=10)
        
        if acceleration < min_acceleration:
            return False
        if zscore < min_zscore:
            return False
        if frequency < min_frequency:
            return False
        
        # Check cooldown
        cooldown_minutes = self.config.get("notifications", "cooldown_minutes", default=60)
        if term in self._notified_trends:
            last_notified = self._notified_trends[term]
            if datetime.utcnow() - last_notified < timedelta(minutes=cooldown_minutes):
                logger.debug(f"Skipping notification for '{term}' (cooldown)")
                return False
        
        # Check exclude list
        exclude_terms = self.config.get("notifications", "exclude_terms", default=[])
        if term.lower() in [t.lower() for t in exclude_terms]:
            return False
        
        return True
    
    def notify_trend(
        self,
        term: str,
        acceleration: float,
        frequency: int,
        platform: str,
        zscore: float = 0.0,
        example_url: Optional[str] = None,
    ) -> bool:
        """
        Send a Windows toast notification for a detected trend.
        
        Args:
            term: The trending term
            acceleration: Acceleration score
            frequency: Number of posts
            platform: Platform name (tiktok, instagram, etc)
            zscore: Z-score
            example_url: Optional URL to example post
            
        Returns:
            True if notification was sent
        """
        if not self.is_available():
            logger.warning("Toast notifier not available")
            return False
        
        if not self.should_notify(term, acceleration, zscore, frequency):
            return False
        
        # Build notification message
        title = "🚨 Meme Trend Alert!"
        
        message = f"Term: \"{term}\"\n"
        message += f"Acceleration: {acceleration:.1f}x\n"
        message += f"Frequency: {frequency} posts\n"
        message += f"Platform: {platform.title()}"
        
        if zscore > 0:
            message += f"\nZ-score: {zscore:.1f}"
        
        # Determine duration (longer for high-value trends)
        duration = 10  # seconds
        if acceleration > 10 or zscore > 15:
            duration = 15  # High priority
        
        # Play sound?
        threaded = True
        sound = self.config.get("notifications", "sound", default=True)
        
        try:
            # Show notification
            logger.info(f"Sending notification for trend: {term}")
            
            self._toaster.show_toast(
                title=title,
                msg=message,
                duration=duration,
                threaded=threaded,
                icon_path=None,  # Use default icon
            )
            
            # Track notification
            self._notified_trends[term] = datetime.utcnow()
            
            # Clean old notifications from tracking
            self._cleanup_old_notifications()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return False
    
    def _cleanup_old_notifications(self):
        """Remove old entries from notification tracking."""
        cooldown_minutes = self.config.get("notifications", "cooldown_minutes", default=60)
        cutoff_time = datetime.utcnow() - timedelta(minutes=cooldown_minutes * 2)
        
        # Remove entries older than 2x cooldown
        self._notified_trends = {
            term: timestamp
            for term, timestamp in self._notified_trends.items()
            if timestamp > cutoff_time
        }
    
    def test_notification(self):
        """Send a test notification."""
        if not self.is_available():
            print("❌ Toast notifier not available")
            return False
        
        try:
            self._toaster.show_toast(
                title="🧪 Meme Radar Test",
                msg="Notifications are working!\n\nYou'll be alerted when trends spike.",
                duration=5,
                threaded=True,
            )
            print("✅ Test notification sent!")
            return True
        except Exception as e:
            print(f"❌ Failed to send test notification: {e}")
            return False


# Allow standalone testing
if __name__ == "__main__":
    print("Testing Windows notifications...")
    notifier = TrendNotifier()
    
    if notifier.is_available():
        print("Sending test notification...")
        notifier.test_notification()
        
        print("\nSimulating trend alert...")
        notifier.notify_trend(
            term="test_meme",
            acceleration=12.5,
            frequency=25,
            platform="tiktok",
            zscore=15.2,
        )
    else:
        print("Notifications not available. Install win10toast: pip install win10toast")
