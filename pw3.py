from playwright.sync_api import sync_playwright
import time
def safe(fn, d=""):
    try: return fn()
    except Exception as e: return d
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=r"C:\Users\asus\AppData\Local\Temp\claude\pwprof1",
        headless=False, channel="chrome",
        args=["--disable-blink-features=AutomationControlled"],
        locale="en-US", viewport={"width":1280,"height":900})
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    safe(lambda: pg.goto("https://www.hltv.org/stats/players/7170/smithzz", wait_until="domcontentloaded", timeout=90000))
    ok=False
    for i in range(30):
        t = safe(lambda: pg.title(), "?")
        if t and "Just a moment" not in t and t!="?":
            ok=True; break
        time.sleep(2)
    print("TITLE:", safe(lambda: pg.title(),"?"), "URL:", pg.url)
    body = safe(lambda: pg.inner_text("body"), "")
    print("LEN", len(body))
    print(body[:1500])
    ctx.close()
