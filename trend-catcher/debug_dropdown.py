"""
Debug script to visually verify which dropdown is being clicked.
Takes screenshots before and after each click to show exactly what's happening.
"""
import asyncio
from playwright.async_api import async_playwright

OUTPUT_DIR = "trend-catcher/debug_screenshots"

async def debug_dropdown():
    """Debug the dropdown selection with screenshots."""
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        print("1. Navigating to Creative Center...")
        await page.goto(
            "https://ads.tiktok.com/business/creativecenter/inspiration/popular/pc/en",
            wait_until="domcontentloaded",
            timeout=60000
        )
        await page.wait_for_timeout(5000)
        
        print("2. Taking screenshot of initial page state...")
        await page.screenshot(path=f"{OUTPUT_DIR}/01_initial.png")
        
        print("3. Scrolling down 400px...")
        await page.evaluate("window.scrollBy(0, 400)")
        await page.wait_for_timeout(1000)
        
        print("4. Taking screenshot after scroll...")
        await page.screenshot(path=f"{OUTPUT_DIR}/02_after_scroll.png")
        
        # Find ALL elements with position info
        print("5. Finding all 'hot' and 'Sort by' elements on page...")
        elements_info = await page.evaluate("""
            () => {
                const result = {
                    hotElements: [],
                    sortByElements: [],
                    daysElements: []
                };
                
                const allElements = Array.from(document.querySelectorAll('div, span'));
                
                for (const el of allElements) {
                    const text = el.innerText ? el.innerText.trim() : '';
                    const rect = el.getBoundingClientRect();
                    
                    if (text === 'hot' && el.offsetParent !== null) {
                        result.hotElements.push({
                            text: text,
                            x: rect.left,
                            y: rect.top,
                            width: rect.width,
                            height: rect.height,
                            className: el.className
                        });
                    }
                    
                    if (text === 'Sort by' && el.offsetParent !== null) {
                        result.sortByElements.push({
                            text: text,
                            x: rect.left,
                            y: rect.top,
                            width: rect.width,
                            height: rect.height
                        });
                    }
                    
                    if (text.includes('days') && el.offsetParent !== null && rect.width < 200) {
                        result.daysElements.push({
                            text: text,
                            x: rect.left,
                            y: rect.top,
                            width: rect.width,
                            height: rect.height
                        });
                    }
                }
                
                return result;
            }
        """)
        
        print("\n=== FOUND ELEMENTS ===")
        print("\n'hot' elements:")
        for el in elements_info['hotElements']:
            print(f"  x={el['x']:.0f}, y={el['y']:.0f}, class={el['className']}")
        
        print("\n'Sort by' elements:")
        for el in elements_info['sortByElements']:
            print(f"  x={el['x']:.0f}, y={el['y']:.0f}")
            
        print("\n'days' elements:")
        for el in elements_info['daysElements']:
            print(f"  x={el['x']:.0f}, y={el['y']:.0f}, text='{el['text']}'")
        
        # Now find the correct "hot" element (the one near "Sort by")
        sort_by = elements_info['sortByElements'][0] if elements_info['sortByElements'] else None
        if sort_by:
            print(f"\n'Sort by' is at x={sort_by['x']:.0f}")
            
            # Find the "hot" that's closest to "Sort by" vertically
            correct_hot = None
            for hot in elements_info['hotElements']:
                if abs(hot['y'] - sort_by['y']) < 50:
                    correct_hot = hot
                    print(f"Found 'hot' near 'Sort by' at x={hot['x']:.0f}, y={hot['y']:.0f}")
                    break
            
            if correct_hot:
                # Highlight and click
                print(f"\n6. Clicking 'hot' at x={correct_hot['x']:.0f}, y={correct_hot['y']:.0f}...")
                
                # Draw a red box around the element we're about to click
                await page.evaluate(f"""
                    () => {{
                        const overlay = document.createElement('div');
                        overlay.id = 'debug-overlay';
                        overlay.style.cssText = `
                            position: fixed;
                            left: {correct_hot['x']}px;
                            top: {correct_hot['y']}px;
                            width: {correct_hot['width']}px;
                            height: {correct_hot['height']}px;
                            border: 3px solid red;
                            background: rgba(255, 0, 0, 0.2);
                            z-index: 99999;
                            pointer-events: none;
                        `;
                        document.body.appendChild(overlay);
                    }}
                """)
                
                await page.screenshot(path=f"{OUTPUT_DIR}/03_highlighted_target.png")
                print("Screenshot saved: 03_highlighted_target.png (red box shows target)")
                
                # Remove overlay
                await page.evaluate("document.getElementById('debug-overlay')?.remove()")
                
                # Click using coordinates
                click_x = correct_hot['x'] + correct_hot['width'] / 2
                click_y = correct_hot['y'] + correct_hot['height'] / 2
                print(f"Clicking at coordinates: ({click_x:.0f}, {click_y:.0f})")
                
                await page.mouse.click(click_x, click_y)
                await page.wait_for_timeout(1500)
                
                await page.screenshot(path=f"{OUTPUT_DIR}/04_after_click.png")
                print("Screenshot saved: 04_after_click.png (shows result of click)")
                
                # Check if dropdown opened
                dropdown_options = await page.evaluate("""
                    () => {
                        const options = document.querySelectorAll('.byted-select-option');
                        return Array.from(options).map(o => o.innerText.trim());
                    }
                """)
                
                print(f"\nDropdown options visible: {dropdown_options}")
                
                if 'Shares' in dropdown_options:
                    print("\n✅ SUCCESS! Sort by dropdown opened correctly!")
                    
                    # Click Shares
                    await page.evaluate("""
                        () => {
                            const options = document.querySelectorAll('.byted-select-option');
                            for (const opt of options) {
                                if (opt.innerText.trim() === 'Shares') {
                                    opt.click();
                                    return true;
                                }
                            }
                            return false;
                        }
                    """)
                    await page.wait_for_timeout(2000)
                    await page.screenshot(path=f"{OUTPUT_DIR}/05_shares_selected.png")
                    print("Screenshot saved: 05_shares_selected.png")
                else:
                    print("\n❌ WRONG DROPDOWN OPENED!")
                    print("The dropdown options don't include 'Shares'")
        
        print("\n=== DEBUG COMPLETE ===")
        print(f"Check screenshots in {OUTPUT_DIR}/ folder")
        
        await page.wait_for_timeout(3000)
        await browser.close()

if __name__ == "__main__":
    import os
    os.makedirs("trend-catcher/debug_screenshots", exist_ok=True)
    asyncio.run(debug_dropdown())
