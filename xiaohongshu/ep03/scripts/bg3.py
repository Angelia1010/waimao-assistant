import asyncio
from playwright.async_api import async_playwright
CSS = """
*{margin:0;box-sizing:border-box}
body{width:1080px;height:1920px;overflow:hidden;font-family:'Noto Sans CJK SC','PingFang SC',sans-serif;color:#EAF0FF;
background:radial-gradient(1200px 700px at 80% -5%,rgba(79,140,255,.38),transparent 60%),radial-gradient(900px 600px at 0% 105%,rgba(255,181,71,.18),transparent 60%),#0B1220}
.top{position:absolute;left:72px;right:72px;top:96px}
.step{display:inline-flex;align-items:center;gap:14px;font-size:30px;font-weight:700;color:#FFB547;letter-spacing:2px}
.step b{display:inline-grid;place-items:center;min-width:52px;height:52px;border-radius:14px;background:#FFB547;color:#0B1220;font-size:28px}
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
def phone_scene(chip, title, sub):
    return page(f"<div class='top'><div class='step'>{chip}</div><h1>{title}</h1><div class='sub'>{sub}</div></div><div class='phone'><div class='screen'></div></div>")
def stepchip(n): return f"<b>{n}</b>步骤"
S = {
 "s1": phone_scene("<b style='width:auto;padding:0 14px'>No.03</b>定制AI小工具", "一键找出 <em>3 处对不上</em>", "4 份单据：PI · 商业发票 · 装箱单 · 报关资料"),
 "s3": phone_scene(stepchip("01"), "放进 4 份单据，<em>一键核对</em>", "PDF、Excel、Word 都能读"),
 "s4": phone_scene(stepchip("02"), "每处都<em>标红</em>", "还告诉你：可能是哪份写错了"),
 "s5": phone_scene(stepchip("03"), "更正消息<em>写好了</em>", "复制给货代 / 报关行就行"),
 "s2": page("""<div style='position:absolute;left:80px;right:80px;top:380px'>
  <div style='font-size:40px;color:#9FB0D0;font-weight:700'>翻评论区，单证员都在说：</div>
  <div style='margin-top:40px;padding:44px 48px;border-radius:32px;background:#16233D;border:2px solid #2A3A5E'>
   <div style='font-size:76px;font-weight:900;line-height:1.3'>“检查了好几遍<br>还是被客户<span style="color:#FF6B6B">挑出错</span>”</div>
   <div style='font-size:46px;color:#C9D5EE;margin-top:34px'>自己很难看出来，最好换个人复核</div></div>
  <div style='font-size:96px;color:#4F8CFF;margin:60px 0 10px;text-align:center'>↓</div>
  <div style='font-size:88px;font-weight:900;line-height:1.25'>所以我做了个<br><span style="color:#FFB547">不会累的复核员</span></div></div>"""),
 "s6": page("""<div style='position:absolute;left:80px;right:80px;top:470px'>
  <div style='font-size:92px;font-weight:900;line-height:1.2'>数字靠代码核对<br><span style="color:#4F8CFF">不靠 AI 猜</span></div>
  <div style='margin-top:80px;font-size:48px;line-height:2;color:#C9D5EE'>
   <div>✓ 单据在你自己的服务器上比对</div><div>✓ 不接外部大模型也能用</div><div>✓ 每个结论都列出原始数字</div></div></div>"""),
 "s8": page("""<div style='position:absolute;left:80px;right:80px;top:470px'>
  <div style='display:inline-block;font-size:40px;font-weight:800;color:#0B1220;background:#FFB547;padding:10px 26px;border-radius:14px'>定制AI小工具 · No.03</div>
  <div style='font-size:110px;font-weight:900;line-height:1.2;margin-top:40px'>单证<br><span style="color:#4F8CFF">复核员</span></div>
  <div style='margin-top:120px;padding:44px 48px;border-radius:32px;background:#16233D;border:2px solid #FFB547'>
   <div style='font-size:50px;font-weight:800;color:#FFB547'>你还想让 AI 帮你复核什么？</div>
   <div style='font-size:36px;color:#9FB0D0;margin-top:16px'>评论区说说，下一期做出来</div></div></div>"""),
}
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome")
        pg = await b.new_page(viewport={"width":1080,"height":1920})
        for k,h in S.items():
            await pg.set_content(h); await pg.wait_for_timeout(200)
            await pg.screenshot(path=f"/home/claude/video3/bg/{k}.png")
        await b.close()
asyncio.run(main())
