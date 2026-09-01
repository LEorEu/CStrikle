from playwright.sync_api import sync_playwright
import time
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=r"C:\Users\asus\AppData\Local\Temp\claude\pwprof1",
        headless=False, channel="chrome",
        args=["--disable-blink-features=AutomationControlled"],
        locale="en-US", viewport={"width":1280,"height":900})
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    pg.goto("https://www.hltv.org/stats/players/7170/smithzz", wait_until="domcontentloaded", timeout=90000)
    for i in range(40):
        if "Just a moment" not in pg.title():
            break
        # try clicking turnstile checkbox inside iframe
        try:
            for fr in pg.frames:
                if "challenges.cloudflare.com" in (fr.url or ""):
                    fr.click("input[type=checkbox]", timeout=1500)
        except Exception: pass
        time.sleep(2)
    print("TITLE:", pg.title())
    print(pg.inner_text("body")[:1200])
    ctx.close()
