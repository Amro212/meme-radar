import asyncio
import argparse
import sys
import os

# Add parent directory to path so we can import modules if run directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sentinel import Sentinel

def main():
    parser = argparse.ArgumentParser(description="TikTok Trend Catcher Sentinel")
    parser.add_argument("--interval", type=int, default=900, help="Check interval in minutes (default 15m)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--no-headless", action="store_false", dest="headless", help="Run browser in visible mode (debug)")
    parser.set_defaults(headless=True)
    
    args = parser.parse_args()
    
    print(f"Starting Trend Catcher Sentinel...")
    print(f"Interval: {args.interval}s")
    print(f"Headless: {args.headless}")
    
    sentinel = Sentinel(check_interval=args.interval, headless=args.headless)
    
    try:
        asyncio.run(sentinel.run_forever())
    except KeyboardInterrupt:
        print("\nSentinel stopped by user.")
    except Exception as e:
        print(f"\nFatal error: {e}")

if __name__ == "__main__":
    main()
