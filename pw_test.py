from playwright.sync_api import sync_playwright
import time, re
with sync_playwright() as p:
    b = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
    ctx = b.new_context(locale="en-US", user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
    pg = ctx.new_page()
    t=time.time()
    r = pg.goto("https://www.hltv.org/stats/players/7170/smithzz", wait_until="domcontentloaded", timeout=60000)
    print("status", r.status if r else None)
    for i in range(20):
        title = pg.title()
        if "Just a moment" not in title:
            break
        time.sleep(1.5)
    print("title:", pg.title(), "elapsed", round(time.time()-t,1))
    txt = pg.inner_text("body")[:1500]
    print(txt)
    ctx.close(); b.close()
