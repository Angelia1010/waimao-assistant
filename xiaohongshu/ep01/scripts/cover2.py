import asyncio
from playwright.async_api import async_playwright
H = """<html><head><style>*{margin:0;box-sizing:border-box}
body{width:1080px;height:1440px;overflow:hidden;font-family:'Noto Sans CJK SC',sans-serif;color:#EAF0FF;
background:radial-gradient(900px 600px at 85% 0%,rgba(79,140,255,.45),transparent 60%),radial-gradient(800px 500px at 0% 100%,rgba(255,181,71,.22),transparent 60%),#0B1220}
.top{position:absolute;left:64px;right:64px;top:70px}
.chip{display:inline-block;font-size:34px;font-weight:800;color:#0B1220;background:#FFB547;padding:8px 22px;border-radius:12px}
.big{font-size:150px;font-weight:900;line-height:1.08;margin-top:22px;letter-spacing:2px}
.big span{color:#4F8CFF}
.line{height:8px;width:200px;background:#FFB547;border-radius:4px;margin-top:30px}
.l{position:absolute;left:64px;top:450px;width:540px}
.ep{font-size:56px;font-weight:900;line-height:1.3}
.pain{margin-top:34px;font-size:40px;font-weight:800;line-height:1.45;color:#FFB547}
.ck{margin-top:44px;font-size:36px;line-height:1.9;color:#C9D5EE}
.ph{position:absolute;right:-20px;top:430px;width:440px;height:840px;border-radius:50px;background:#05080F;padding:13px;
transform:rotate(6deg);box-shadow:0 0 0 3px #2A3550,0 40px 100px rgba(0,0,0,.6),0 0 140px rgba(79,140,255,.3)}
.ph img{width:100%;height:100%;object-fit:cover;object-position:top;border-radius:38px}
.b{position:absolute;left:64px;bottom:90px;font-size:38px;font-weight:800;padding:20px 32px;border-radius:24px;background:#16233D;border:2px solid #4F8CFF}
.d{position:absolute;right:40px;bottom:30px;font-size:22px;color:#6B7A99}
</style></head><body>
<div class=top><div class=chip>No.01 · 外贸篇</div><div class=big>定制<span>AI小工具</span></div><div class=line></div></div>
<div class=l><div class=ep>第1期<br>外贸订单助手</div>
<div class=pain>报价后客户已读不回？<br>AI 帮你排好每天跟谁</div>
<div class=ck>✓ 询盘自动分级<br>✓ 一键英文报价单<br>✓ 跟进话术先写好</div></div>
<div class=ph><img src="file:///home/claude/video/cover_shot.jpg"></div>
<div class=b>你的行业也想要一个？👇</div>
<div class=d>演示数据</div></body></html>"""
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--allow-file-access-from-files"])
        pg = await b.new_page(viewport={"width":1080,"height":1440})
        open("/home/claude/video/cover2.html","w").write(H)
        await pg.goto("file:///home/claude/video/cover2.html"); await pg.wait_for_timeout(400)
        await pg.screenshot(path="/home/claude/video/定制AI小工具No01_封面.png"); await b.close()
asyncio.run(main())
