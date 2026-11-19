import json, os, subprocess
from PIL import Image, ImageDraw
V = "/home/claude/video"; os.makedirs(f"{V}/parts", exist_ok=True)
ENC = ["-c:v","libx264","-crf","18","-preset","veryfast","-pix_fmt","yuv420p","-r","30"]
def run(cmd, out):
    tmp = out.replace(".mp4", ".tmp.mp4")
    subprocess.run(cmd + [tmp, "-y", "-loglevel", "error"], check=True); os.rename(tmp, out)
# 带“屏幕挖空”的前景层
for k in ["s2","s3","s4","s6"]:
    im = Image.open(f"{V}/bg/{k}.png").convert("RGBA")
    m = Image.new("L", im.size, 255); ImageDraw.Draw(m).rounded_rectangle([168,420,168+744,420+1374], 46, fill=0)
    im.putalpha(m); im.save(f"{V}/bg/{k}_over.png")
def frames_list(d, t_from, t_to, hold):
    j = json.load(open(f"{V}/cap/{d}/index.json")); fr = j["frames"]; end = min(t_to, j["end"])
    sel = [(f,t) for f,t in fr if t <= end]
    # 起点之前最后一帧作为第一帧
    start = [x for x in sel if x[1] <= t_from][-1:]; sel = start + [x for x in sel if x[1] > t_from]
    lines = []
    for i,(f,t) in enumerate(sel):
        t0 = max(t, t_from); t1 = sel[i+1][1] if i+1 < len(sel) else end + hold
        lines += [f"file '{f}'", f"duration {max(t1-t0, 0.001):.4f}"]
    lines.append(f"file '{sel[-1][0]}'")
    p = f"{V}/parts/{d}.txt"; open(p,"w").write("\n".join(lines)); return p, end + hold - t_from
def phone_scene(k, d, t_from, t_to, hold):
    lst, dur = frames_list(d, t_from, t_to, hold)
    f = (f"[1:v]fps=30,scale=744:1374,setsar=1[s];[0:v][s]overlay=168:420[a];[a][2:v]overlay=0:0,"
         f"trim=duration={dur:.3f},fade=in:d=0.35,fade=out:st={dur-0.35:.3f}:d=0.35,format=yuv420p")
    run(["ffmpeg","-f","lavfi","-i","color=c=0x0F1A2E:s=1080x1920:r=30","-f","concat","-safe","0","-i",lst,
         "-framerate","30","-i",f"{V}/bg/{k}_over.png","-filter_complex",f]+ENC, f"{V}/parts/{k}.mp4")
    return dur
def still(k, dur):
    run(["ffmpeg","-framerate","30","-i",f"{V}/bg/{k}.png","-vf",
         f"format=yuv420p,loop=-1:1,trim=duration={dur},fade=in:d=0.4,fade=out:st={dur-0.4}:d=0.4"]+ENC, f"{V}/parts/{k}.mp4")
def pdf_scene(dur=5.0):
    q = Image.open(f"{V}/quote_p1.png").convert("RGB"); q = q.crop((80,80,1460,1250)).resize((936,int(1170*936/1380)))
    card = Image.new("RGB",(960,q.height+24),"#FFFFFF"); card.paste(q,(12,12)); card.save(f"{V}/parts/pdfcard.png")
    # 卡片从 y=520 缓慢上移到 y=470，同时放大高亮总价
    f = (f"[1:v]format=rgba,loop=-1:1[c];[0:v][c]overlay=x=60:y='540-14*t':shortest=0,trim=duration={dur},"
         f"drawbox=x=60+12+665:y='540-14*t+12+548':w=280:h=62:color=0xFFB547@0.9:t=5:enable='gte(t,1.6)',"
         f"fade=in:d=0.35,fade=out:st={dur-0.35}:d=0.35,format=yuv420p")
    run(["ffmpeg","-framerate","30","-loop","1","-t",str(dur),"-i",f"{V}/bg/s5.png","-framerate","30","-i",f"{V}/parts/pdfcard.png",
         "-filter_complex",f]+ENC, f"{V}/parts/s5.mp4")
still("s1", 3.6)
d2 = phone_scene("s2","s2_inbox",1.0,9.6,0.4)
d3 = phone_scene("s3","s3_paste",0.5,6.4,1.6)
d4 = phone_scene("s4","s4_quote",0.5,7.4,0.4)
pdf_scene(5.0)
d6 = phone_scene("s6","s6_follow",0.4,8.8,0.8)
still("s8", 5.6)
open(f"{V}/parts/all.txt","w").write("\n".join(f"file '{V}/parts/{k}.mp4'" for k in ["s1","s2","s3","s4","s5","s6","s8"]))
run(["ffmpeg","-f","concat","-safe","0","-i",f"{V}/parts/all.txt","-c","copy"], f"{V}/parts/video_noaudio.mp4")
run(["ffmpeg","-i",f"{V}/parts/video_noaudio.mp4","-f","lavfi","-i","anullsrc=r=44100:cl=stereo","-map","0:v","-map","1:a",
     "-c:v","copy","-c:a","aac","-b:a","128k","-shortest","-movflags","+faststart"], f"{V}/外贸AI订单助手_小红书竖屏.mp4")
print("durations", d2, d3, d4, d6)
