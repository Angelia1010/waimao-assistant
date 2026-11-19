import asyncio
from playwright.async_api import async_playwright
CSS = """
*{margin:0;box-sizing:border-box}
body{width:1080px;height:1920px;overflow:hidden;font-family:'Noto Sans CJK SC','PingFang SC',sans-serif;color:#EAF0FF;
background:radial-gradient(1200px 700px at 80% -5%,rgba(79,140,255,.38),transparent 60%),radial-gradient(900px 600px at 0% 105%,rgba(255,181,71,.18),transparent 60%),#0B1220}
.top{position:absolute;left:72px;right:72px;top:96px}
.step{display:inline-flex;align-items:center;gap:14px;font-size:30px;font-weight:700;color:#FFB547;letter-spacing:2px}
.step b{display:inline-grid;place-items:center;width:52px;height:52px;border-radius:14px;background:#FFB547;color:#0B1220;font-size:28px}
h1{font-size:76px;line-height:1.18;font-weight:900;margin-top:26px;letter-spacing:1px}
h1 em{font-style:normal;color:#4F8CFF}
.sub{font-size:36px;color:#9FB0D0;margin-top:18px}
.phone{position:absolute;left:148px;top:400px;width:784px;height:1414px;border-radius:64px;background:#05080F;
box-shadow:0 0 0 3px #2A3550,0 40px 120px rgba(0,0,0,.6),0 0 160px rgba(79,140,255,.25)}
.screen{position:absolute;left:20px;top:20px;width:744px;height:1374px;border-radius:46px;background:#0F1A2E}
.demo{position:absolute;right:56px;bottom:40px;font-size:24px;color:#6B7A99}
.card{position:absolute;left:72px;right:72px;top:420px}
"""
def page(body): return f"<html><head><style>{CSS}</style></head><body>{body}<div class='demo'>演示数据 · 非真实客户</div></body></html>"
def scene(n, title, sub, phone=True):
    return page(f"<div class='top'><div class='step'><b>{n}</b>步骤</div><h1>{title}</h1><div class='sub'>{sub}</div></div>" + ("<div class='phone'><div class='screen'></div></div>" if phone else ""))
S = {
 "s2": scene("01", "询盘进来，<em>AI 先分级</em>", "A 级先报价 · 推广骚扰自动过滤"),
 "s3": scene("02", "聊天询盘，<em>粘贴就行</em>", "WhatsApp / 微信 · AI 提取产品、数量、目标价"),
 "s4": scene("03", "点一下，<em>生成英文报价单</em>", "PDF + 报价邮件草稿一起出"),
 "s5": scene("04", "价格取自<em>你的产品库</em>", "不让 AI 编价格 · 自动算总价", phone=False),
 "s6": scene("05", "每天告诉你：<em>今天该跟谁</em>", "按 A/B/C 级排节奏 · 话术先写好"),
 "s1": page("""<div style='position:absolute;left:80px;right:80px;top:470px'>
  <div style='font-size:40px;color:#9FB0D0;font-weight:700'>外贸工厂的老问题</div>
  <div style='font-size:118px;font-weight:900;line-height:1.15;margin-top:30px'>报价发出去<br>客户<span style="color:#FFB547">已读不回</span>？</div>
  <div style='height:6px;width:160px;background:#4F8CFF;border-radius:3px;margin:70px 0 60px'></div>
  <div style='font-size:56px;font-weight:800;line-height:1.4'>我给工厂做了个<br><span style="color:#4F8CFF">AI 订单助手</span></div>
  <div style='display:flex;gap:20px;margin-top:60px;font-size:34px'>
   <span style='padding:14px 26px;border-radius:40px;background:#16233D;border:2px solid #2A3A5E'>询盘分级</span>
   <span style='padding:14px 26px;border-radius:40px;background:#16233D;border:2px solid #2A3A5E'>一键报价</span>
   <span style='padding:14px 26px;border-radius:40px;background:#16233D;border:2px solid #2A3A5E'>跟进提醒</span></div></div>"""),
 "s8": page("""<div style='position:absolute;left:80px;right:80px;top:430px'>
  <div style='font-size:96px;font-weight:900;line-height:1.2'>AI 起草<br><span style="color:#4F8CFF">人来确认</span></div>
  <div style='margin-top:70px;font-size:44px;line-height:1.9;color:#C9D5EE'>
   <div>✓ 数据存在工厂自己的服务器</div><div>✓ 报价邮件业务员确认后才发</div><div>✓ 价格只取自产品库</div></div>
  <div style='margin-top:110px;padding:44px 48px;border-radius:32px;background:#16233D;border:2px solid #FFB547'>
   <div style='font-size:50px;font-weight:800;color:#FFB547'>你最想把哪件事交给 AI？</div>
   <div style='font-size:36px;color:#9FB0D0;margin-top:16px'>评论区聊聊，我挑几个做出来</div></div></div>"""),
}
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome")
        pg = await b.new_page(viewport={"width":1080,"height":1920})
        for k,h in S.items():
            await pg.set_content(h); await pg.wait_for_timeout(200)
            await pg.screenshot(path=f"/home/claude/video/bg/{k}.png")
        await b.close()
asyncio.run(main())
