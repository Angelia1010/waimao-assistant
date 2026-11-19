import asyncio, base64, json, os, sys, time
from playwright.async_api import async_playwright
B = "http://127.0.0.1:8199"
OUT = "/home/claude/video/cap"
W, H, DPR = 390, 720, 2

class Rec:
    def __init__(self, page, name):
        self.page, self.name, self.frames = page, name, []
        self.dir = os.path.join(OUT, name); os.makedirs(self.dir, exist_ok=True)
        for f in os.listdir(self.dir): os.remove(os.path.join(self.dir, f))
    async def start(self):
        self.cdp = await self.page.context.new_cdp_session(self.page)
        self.cdp.on("Page.screencastFrame", self.on_frame)
        self.t0 = time.monotonic()
        await self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": W*DPR, "maxHeight": H*DPR, "everyNthFrame": 1})
    def on_frame(self, p):
        t = time.monotonic() - self.t0
        fn = os.path.join(self.dir, f"{len(self.frames):05d}.jpg")
        open(fn, "wb").write(base64.b64decode(p["data"]))
        self.frames.append((fn, t))
        asyncio.ensure_future(self.cdp.send("Page.screencastFrameAck", {"sessionId": p["sessionId"]}))
    async def stop(self):
        t_end = time.monotonic() - self.t0
        await self.cdp.send("Page.stopScreencast")
        json.dump({"frames": self.frames, "end": t_end}, open(os.path.join(self.dir, "index.json"), "w"))
        print(self.name, len(self.frames), "frames", round(t_end, 1), "s")

async def wait(s): await asyncio.sleep(s)

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome")
        ctx = await b.new_context(viewport={"width": W, "height": H}, device_scale_factor=DPR, is_mobile=True, has_touch=True)
        pg = await ctx.new_page()
        # 首页收件箱：录制时把动画节奏加快
        async def fast(route):
            r = await route.fetch(); body = (await r.text()).replace("}, 1700);", "}, 900);")
            await route.fulfill(response=r, body=body)
        await pg.route(B + "/", fast)
        await pg.goto(B + "/"); await pg.evaluate("document.querySelector('#inbox').closest('.card').scrollIntoView({block:'center'})")
        await pg.evaluate("window.scrollBy(0, 40)")
        await wait(0.3)
        await pg.goto(B + "/"); await pg.evaluate("document.querySelector('#inbox').closest('.card').scrollIntoView({block:'center'})")
        r = Rec(pg, "s2_inbox"); await r.start(); await wait(10.5); await r.stop()

        # 登录
        await pg.goto(B + "/app"); await pg.wait_for_selector("#loginForm")
        await pg.fill("#lu", "lily"); await pg.fill("#lp", "demo-pass-123"); await pg.click("button[type=submit]")
        await pg.wait_for_selector(".metrics")

        # 录入 WhatsApp 询盘
        await pg.goto(B + "/app#/new"); await pg.wait_for_selector("#nText"); await wait(0.6)
        r = Rec(pg, "s3_paste"); await r.start(); await wait(0.8)
        await pg.select_option("#nSrc", "WhatsApp"); await wait(0.5)
        text = open("/home/claude/rec/demo/whatsapp_chile.txt").read()
        await pg.click("#nText")
        for i in range(0, len(text), 18):
            await pg.fill("#nText", text[:i+18]); await wait(0.035)
        await wait(0.6)
        await pg.click("#newForm button[type=submit]")
        await pg.wait_for_selector("#nResult .lv", timeout=15000); await wait(0.4)
        await pg.evaluate("document.querySelector('#nResult').scrollIntoView({behavior:'smooth', block:'start'})")
        await wait(3.2); await r.stop()

        # 一键报价
        await pg.goto(B + "/app#/leads"); await pg.wait_for_selector("table.tbl"); await wait(0.5)
        r = Rec(pg, "s4_quote"); await r.start(); await wait(0.8)
        await pg.click("tr:has-text('Nordbau')"); await pg.wait_for_selector("#ldQuote"); await wait(1.4)
        await pg.evaluate("document.querySelector('#ldQuote').scrollIntoView({behavior:'smooth', block:'center'})"); await wait(1.0)
        await pg.click("#ldQuote"); await pg.wait_for_selector("text=复制报价邮件", timeout=15000); await wait(0.6)
        await pg.evaluate("document.querySelector('#ldQuote').closest('.card').scrollIntoView({behavior:'smooth', block:'start'})")
        await wait(3.0); await r.stop()
        pdf_url = await pg.get_attribute("a:has-text('查看 PDF')", "href")
        await pg.keyboard.press("Escape")

        # 每日跟进
        await pg.goto(B + "/app#/dashboard"); await pg.wait_for_selector("#dueList"); await wait(0.5)
        r = Rec(pg, "s6_follow"); await r.start(); await wait(0.6)
        await pg.evaluate("document.querySelector('#dueList').closest('.card').scrollIntoView({behavior:'smooth', block:'start'})"); await wait(1.2)
        await pg.click("#dueList [data-draft]"); await pg.wait_for_selector("#dueList .draft", timeout=15000); await wait(0.4)
        await pg.evaluate("document.querySelector('#dueList').closest('.card').scrollIntoView({behavior:'smooth', block:'start'})"); await wait(2.6)
        btn = await pg.query_selector("#dueList .fu [data-copy]")
        if btn: await btn.click(); await wait(1.2)
        await pg.click("#dueList [data-followed]"); await wait(2.6); await r.stop()

        # 报价单 PDF 文件
        resp = await pg.request.get(B + pdf_url)
        open("/home/claude/video/quote.pdf", "wb").write(await resp.body())
        await b.close()
asyncio.run(main())
