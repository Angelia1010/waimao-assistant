import asyncio, base64, json, os, time, glob
from playwright.async_api import async_playwright
B = "http://127.0.0.1:8199"; OUT = "/home/claude/video3/cap"; W, H, DPR = 390, 720, 2
DOCS = sorted(glob.glob("/home/claude/waimao-assistant/demo/docs/*"))
DOCS = [d for k in ("PI_", "CI_", "PL_", "报关") for d in DOCS if os.path.basename(d).startswith(k)]

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
        fn = os.path.join(self.dir, f"{len(self.frames):05d}.jpg")
        open(fn, "wb").write(base64.b64decode(p["data"])); self.frames.append((fn, time.monotonic() - self.t0))
        asyncio.ensure_future(self.cdp.send("Page.screencastFrameAck", {"sessionId": p["sessionId"]}))
    async def stop(self):
        end = time.monotonic() - self.t0
        await self.cdp.send("Page.stopScreencast")
        json.dump({"frames": self.frames, "end": end}, open(os.path.join(self.dir, "index.json"), "w"))
        print(self.name, len(self.frames), round(end, 1))

w = asyncio.sleep
async def smooth(pg, sel, i=0, block="start"):
    await pg.evaluate(f"document.querySelectorAll({json.dumps(sel)})[{i}].scrollIntoView({{behavior:'smooth', block:'{block}'}})")

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome")
        ctx = await b.new_context(viewport={"width": W, "height": H}, device_scale_factor=DPR, is_mobile=True, has_touch=True)
        pg = await ctx.new_page()
        await pg.goto(B + "/app"); await pg.fill("#lu", "lily"); await pg.fill("#lp", "demo-pass-123"); await pg.click("button[type=submit]")
        await pg.wait_for_selector(".metrics")
        await pg.goto(B + "/app#/doccheck"); await pg.wait_for_selector("#dcInput", state="attached"); await w(0.8)
        await pg.evaluate("document.querySelector('#topnav').scrollLeft = 260")
        # 场景 3：放入单据 → 核对 → 结果
        r = Rec(pg, "s3_run"); await r.start(); await w(0.8)
        await pg.evaluate("window.scrollTo({top: 60, behavior:'smooth'})"); await w(0.4)
        for d in DOCS:
            await pg.set_input_files("#dcInput", [d]); await w(0.45)
        await w(0.6)
        await pg.click("#dcRun")
        await pg.wait_for_selector(".dc-sum", timeout=20000); await w(2.6)
        await r.stop()
        # 场景 4：逐处看问题
        r = Rec(pg, "s4_issues"); await r.start(); await w(0.3)
        await smooth(pg, ".dc-issue", 0); await w(2.0)
        await smooth(pg, ".dc-issue", 1); await w(2.3)
        await smooth(pg, ".dc-issue", 2); await w(2.4)
        await r.stop()
        # 场景 5：更正消息
        r = Rec(pg, "s5_mail"); await r.start(); await w(0.3)
        await smooth(pg, ".dc-mail"); await w(1.6)
        await pg.click("[data-copyemail]"); await w(2.4)
        await r.stop()
        # 静帧：结果概览（开头和封面用）
        await pg.evaluate("window.scrollTo(0, document.querySelector('#dcResult').getBoundingClientRect().top + scrollY - 66)"); await w(0.8)
        await pg.screenshot(path="/home/claude/video3/report_top.jpg", type="jpeg", quality=92)
        await smooth(pg, ".dc-issue"); await w(1.0)
        await pg.screenshot(path="/home/claude/video3/report_issue.jpg", type="jpeg", quality=92)
        await b.close()
asyncio.run(main())
