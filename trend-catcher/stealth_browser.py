"""
Anti-bot playwright configuration with stealth mode
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

def load_cookies():
    """Load TikTok cookies from cookies.json file."""
    cookie_file = Path(__file__).parent / "cookies.json"
    if cookie_file.exists():
        with open(cookie_file, 'r') as f:
            cookies = json.load(f)
            # Convert cookie format for playwright
            playwright_cookies = []
            for cookie in cookies:
                # Convert sameSite to valid playwright values
                same_site = cookie.get('sameSite', 'None')
                if same_site == 'no_restriction':
                    same_site = 'None'
                elif same_site == 'unspecified':
                    same_site = 'None' if cookie.get('secure') else 'Lax'
                elif same_site not in ['Strict', 'Lax', 'None']:
                    same_site = 'Lax'
                
                playwright_cookies.append({
                    'name': cookie['name'],
                    'value': cookie['value'],
                    'domain': cookie['domain'],
                    'path': cookie['path'],
                    'expires': cookie.get('expirationDate', -1),
                    'httpOnly': cookie.get('httpOnly', False),
                    'secure': cookie.get('secure', False),
                    'sameSite': same_site
                })
            return playwright_cookies
    return []

async def create_stealth_browser(p, headless=False):
    """Create a browser with anti-bot detection measures."""
    
    browser = await p.chromium.launch(
        headless=headless,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process'
        ]
    )
    
    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        locale="en-US",
        timezone_id="America/New_York",
        permissions=["geolocation"],
        geolocation={"latitude": 40.7128, "longitude": -74.0060},  # New York
        color_scheme="dark",
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Sec-Fetch-Dest": "document",
        }
    )
    
    # Load cookies to appear as logged-in user
    cookies = load_cookies()
    if cookies:
        await context.add_cookies(cookies)
    
    return browser, context


async def add_stealth_scripts(page):
    """Add JavaScript to hide automation indicators."""
    await page.add_init_script("""
        // Overwrite the `plugins` property to use a custom getter.
        Object.defineProperty(navigator, 'webdriver', {
            get: () => false,
        });
        
        // Overwrite the `plugins` property to use a custom getter.
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });
        
        // Overwrite the `languages` property to use a custom getter.
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });
        
        // Pass the Chrome Test.
        window.chrome = {
            runtime: {},
        };
        
        // Pass the Permissions Test.
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
    """)
