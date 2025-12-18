import json
import os
import logging
from pathlib import Path
from typing import Optional, List, Dict
from TikTokApi import TikTokApi

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tiktok_auth")

COOKIES_FILE = "cookies.json"

def get_cookies_path() -> Path:
    """Get path to cookies file in current directory."""
    return Path(__file__).parent / COOKIES_FILE

def load_cookies() -> Optional[Dict]:
    """
    Load cookies from JSON file.
    Returns a dictionary suitable for TikTokApi injection or specific token extraction.
    """
    path = get_cookies_path()
    if not path.exists():
        logger.error(f"Cookies file not found at {path}")
        return None
    
    try:
        with open(path, 'r') as f:
            cookies = json.load(f)
        
        cookie_dict = {}
        ms_token = None
        
        for cookie in cookies:
            name = cookie.get('name', '')
            value = cookie.get('value', '')
            if name and value:
                cookie_dict[name] = value
                if name == 'msToken':
                    ms_token = value
        
        return {
            'cookies': cookie_dict,
            'ms_token': ms_token
        }
        
    except Exception as e:
        logger.error(f"Failed to load cookies: {e}")
        return None

async def init_api(headless: bool = False, num_sessions: int = 1) -> TikTokApi:
    """
    Initialize TikTokApi session.
    
    Args:
        headless: Whether to run browser in headless mode.
        num_sessions: Number of browser pages to open.
        
    Returns:
        TikTokApi instance with active session.
    """
    api = TikTokApi()
    
    cookie_data = load_cookies()
    ms_token = None
    
    if cookie_data:
        ms_token = cookie_data.get('ms_token')
        logger.info("Loaded cookies and ms_token from file")
    
    ms_tokens = [ms_token] if ms_token else []
    
    # Create session
    await api.create_sessions(
        ms_tokens=ms_tokens,
        num_sessions=num_sessions,
        sleep_after=3,
        headless=headless,
        browser="chromium"
    )
    
    return api
