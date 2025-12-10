from meme_radar.collectors.tiktok import TikTokCollector
import asyncio
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

def test_tiktok():
    print("Initializing TikTok Collector...")
    try:
        from TikTokApi import TikTokApi
        print("Successfully imported TikTokApi")
    except ImportError as e:
        print(f"Failed to import TikTokApi: {e}")
    except Exception as e:
        print(f"Failed to import TikTokApi (Unknown error): {e}")

    collector = TikTokCollector()
    
    if not collector.is_available():
        print("TikTok collector says it's NOT available (missing TikTokApi module?).")
        return

    print("TikTok collector is available. Attempting collection...")
    # Mock config
    from unittest.mock import MagicMock
    collector.config = MagicMock()
    collector.config.get.return_value = True # enabled
    
    # We need to manually inject config behavior or use the real one, 
    # but the collector reads config internally via self.config.get
    # The BaseCollector initializes self.config from meme_radar.config.config
    # So it should work with real config.
    
    try:
        # Run collection
        # Note: collector.collect() creates its own loop, which might conflict if we are already async.
        # But here we are calling it from a script. collector.collect() is synchronous wrapper.
        
        print("Calling collect()...")
        result = collector.collect()
        
        print(f"Collection complete.")
        print(f"Posts: {len(result.posts)}")
        print(f"Errors: {result.errors}")
        
    except Exception as e:
        print(f"Fatal error during collection: {e}")

if __name__ == "__main__":
    test_tiktok()
