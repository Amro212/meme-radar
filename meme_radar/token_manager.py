"""
Token Manager for TikTok API.

Handles automatic ms_token refresh using Playwright browser automation.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class TokenManager:
    """
    Manages TikTok ms_token lifecycle.
    
    Extracts fresh tokens from browser sessions when needed.
    """
    
    # Token refresh interval (1 hour)
    REFRESH_INTERVAL_HOURS = 1
    
    def __init__(self):
        self._last_refresh: Optional[datetime] = None
        self._cached_token: Optional[str] = None
    
    def needs_refresh(self) -> bool:
        """Check if token needs to be refreshed."""
        if self._last_refresh is None:
            return True
        
        age = datetime.utcnow() - self._last_refresh
        return age > timedelta(hours=self.REFRESH_INTERVAL_HOURS)
    
    async def get_fresh_token(self) -> Optional[str]:
        """
        Extract ms_token from TikTok using Playwright.
        
        Returns the token string or None if extraction fails.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install")
            return None
        
        logger.info("Extracting fresh ms_token from TikTok...")
        
        try:
            async with async_playwright() as p:
                # Launch browser
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = await context.new_page()
                
                # Navigate to TikTok
                await page.goto("https://www.tiktok.com/", wait_until="networkidle", timeout=30000)
                
                # Wait for page to fully load and set cookies
                await asyncio.sleep(3)
                
                # Extract cookies
                cookies = await context.cookies()
                
                # Find ms_token
                ms_token = None
                for cookie in cookies:
                    if cookie.get("name") == "msToken":
                        ms_token = cookie.get("value")
                        break
                
                await browser.close()
                
                if ms_token:
                    logger.info(f"Successfully extracted ms_token ({len(ms_token)} chars)")
                    self._cached_token = ms_token
                    self._last_refresh = datetime.utcnow()
                    return ms_token
                else:
                    logger.warning("ms_token cookie not found in response")
                    return None
                    
        except Exception as e:
            logger.error(f"Failed to extract ms_token: {e}")
            return None
    
    def get_token_sync(self) -> Optional[str]:
        """
        Synchronous wrapper for getting a fresh token.
        
        Handles the asyncio event loop setup for Windows and existing loops.
        """
        # Use cached token if still fresh
        if not self.needs_refresh() and self._cached_token:
            logger.debug("Using cached ms_token")
            return self._cached_token
        
        # Set Windows event loop policy for Playwright
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
        # Check if we're already in an event loop
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context - can't nest easily
            # Return cached or None, let caller handle
            logger.warning("Cannot refresh token from async context, using cached")
            return self._cached_token
        except RuntimeError:
            # No loop running, safe to create one
            pass
        
        # Run async extraction
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            token = loop.run_until_complete(self.get_fresh_token())
            loop.close()
            return token
        except Exception as e:
            logger.error(f"Token extraction failed: {e}")
            return None
    
    def get_cached_token(self) -> Optional[str]:
        """Get the currently cached token without refreshing."""
        return self._cached_token
    
    def get_token_age_minutes(self) -> Optional[float]:
        """Get the age of the current token in minutes."""
        if self._last_refresh is None:
            return None
        age = datetime.utcnow() - self._last_refresh
        return age.total_seconds() / 60


# Global token manager instance
_token_manager: Optional[TokenManager] = None


def get_token_manager() -> TokenManager:
    """Get the global token manager instance."""
    global _token_manager
    if _token_manager is None:
        _token_manager = TokenManager()
    return _token_manager
