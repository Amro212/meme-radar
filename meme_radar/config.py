"""
Configuration loader for Meme Radar.

Loads settings from config/config.yaml and environment variables.
"""

import os
from pathlib import Path
from typing import Any

import yaml


class Config:
    """Configuration manager for Meme Radar."""
    
    _instance = None
    _config: dict = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance
    
    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        config_path = Path(__file__).parent.parent / "config" / "config.yaml"
        
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        with open(config_path, "r") as f:
            self._config = yaml.safe_load(f)
        
        # Override with environment variables where applicable
        self._apply_env_overrides()
    
    def _apply_env_overrides(self) -> None:
        """Override config values with environment variables."""
        # Reddit credentials
        if os.getenv("REDDIT_CLIENT_ID"):
            self._config["reddit"]["client_id"] = os.getenv("REDDIT_CLIENT_ID")
        if os.getenv("REDDIT_CLIENT_SECRET"):
            self._config["reddit"]["client_secret"] = os.getenv("REDDIT_CLIENT_SECRET")
        if os.getenv("REDDIT_USER_AGENT"):
            self._config["reddit"]["user_agent"] = os.getenv("REDDIT_USER_AGENT")
        
        # Database URL override
        if os.getenv("DATABASE_URL"):
            self._config["database"]["url"] = os.getenv("DATABASE_URL")
    
    def get(self, *keys: str, default: Any = None) -> Any:
        """
        Get a configuration value by nested keys.
        
        Example:
            config.get("reddit", "subreddits")
            config.get("analysis", "z_score_threshold", default=2.0)
        """
        value = self._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
    
    @property
    def database_url(self) -> str:
        return self.get("database", "url", default="sqlite:///meme_radar.db")
    
    @property
    def scheduler_interval(self) -> int:
        return self.get("scheduler", "interval_minutes", default=30)
    
    @property
    def time_window_minutes(self) -> int:
        return self.get("analysis", "time_window_minutes", default=30)
    
    @property
    def history_windows(self) -> int:
        return self.get("analysis", "history_windows", default=6)
    
    def reload(self) -> None:
        """Reload configuration from file."""
        self._load_config()


# Singleton instance
config = Config()
