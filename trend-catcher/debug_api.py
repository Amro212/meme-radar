import asyncio
import logging
from utils_auth import init_api

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("debug_api")

async def test_endpoints():
    logger.info("Initializing API...")
    api = await init_api(headless=False)
    
    try:
        # TEST 1: User Info (Usually easiest)
        logger.info("--- TEST 1: User Info ---")
        try:
            user = api.user("tiktok")
            async for video in user.videos(count=1):
                logger.info(f"SUCCESS: Got video {video.id} from user @tiktok")
                break
        except Exception as e:
            logger.error(f"FAIL: User fetch failed: {e}")

        # TEST 2: Hashtag (Medium difficulty)
        logger.info("--- TEST 2: Hashtag ---")
        try:
            tag = api.hashtag(name="viral")
            async for video in tag.videos(count=1):
                logger.info(f"SUCCESS: Got video {video.id} from #viral")
                break
        except Exception as e:
            logger.error(f"FAIL: Hashtag fetch failed: {e}")
            
        # TEST 3: Trending (Hardest)
        logger.info("--- TEST 3: Trending ---")
        try:
            async for video in api.trending.videos(count=1):
                logger.info(f"SUCCESS: Got trending video {video.id}")
                break
        except Exception as e:
            logger.error(f"FAIL: Trending fetch failed: {e}")
            
    finally:
        await api.close_sessions()

if __name__ == "__main__":
    asyncio.run(test_endpoints())
