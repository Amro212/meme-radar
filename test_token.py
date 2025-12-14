"""Test token refresh functionality."""
from meme_radar.token_manager import get_token_manager

print("Testing token refresh...")
tm = get_token_manager()
token = tm.get_token_sync()

if token:
    print(f"Token obtained: True")
    print(f"Token length: {len(token)}")
    print(f"Token preview: {token[:50]}...")
else:
    print("Token obtained: False")
    print("Token refresh failed - check Playwright installation")
