import numpy as np
from scipy.signal import butter, sosfilt
from scipy.io import wavfile
SR=44100; T=36.0; N=int(SR*T); rng=np.random.default_rng(7)
BPM=112; beat=60/BPM; bar=4*beat
L=np.zeros(N); R=np.zeros(N)
def mtof(m): return 440*2**((m-69)/12)
def lp(x,f,o=2): return sosfilt(butter(o,f,'low',fs=SR,output='sos'),x)
def hp(x,f,o=2): return sosfilt(butter(o,f,'high',fs=SR,output='sos'),x)
def add(sig,t,pan=0.0,gain=1.0):
    i=int(t*SR); 
    if i>=N: return
    s=sig[:N-i]*gain; L[i:i+len(s)]+=s*(1-pan)/1; R[i:i+len(s)]+=s*(1+pan)/1
# 和弦进行 Am - F - C - G（每小节一个）
prog=[[57,60,64],[53,57,60],[48,52,55],[55,59,62]]
roots=[45,41,48,43]
DROP=3.6; BREAK=(27.0,31.2); OUT=31.2
nb=int(T/bar)+1
# Pad
for b in range(nb):
    t0=b*bar; ch=prog[b%4]; d=bar+0.3; tt=np.arange(int(d*SR))/SR
    s=np.zeros_like(tt)
    for m in ch:
        for det in (-0.08,0.08):
            ph=2*np.pi*mtof(m+12)*(1+det/100)*tt
            s+=2*(ph/(2*np.pi)%1)-1
    env=np.minimum(1,tt/0.4)*np.minimum(1,(d-tt)/0.4)
    s=lp(s*env,1400)*0.035
    add(s,t0,pan=-0.2,gain=0.9 if t0<OUT else 0.7); add(s,t0+0.012,pan=0.2,gain=0.9 if t0<OUT else 0.7)
# 拨弦琶音（8 分音符）
pat=[0,1,2,1,0,2,1,2]
for b in range(nb):
    ch=prog[b%4]
    for k in range(8):
        t=b*bar+k*beat/2
        if t>=T: break
        m=ch[pat[k]]+24; d=0.5; tt=np.arange(int(d*SR))/SR
        s=(np.sin(2*np.pi*mtof(m)*tt)+0.3*np.sin(2*np.pi*mtof(m)*2*tt))*np.exp(-tt*7)
        g=0.05 if t<DROP else 0.065
        add(s,t,pan=0.35 if k%2 else -0.35,gain=g)
        add(s,t+beat*0.75,pan=-0.35 if k%2 else 0.35,gain=g*0.35)  # 回声
# 鼓和贝斯（DROP 之后）
def kick():
    d=0.35; tt=np.arange(int(d*SR))/SR; f=50+90*np.exp(-tt*30)
    return np.sin(2*np.pi*np.cumsum(f)/SR)*np.exp(-tt*9)
def clap():
    d=0.25; tt=np.arange(int(d*SR))/SR; n=rng.standard_normal(len(tt))
    return hp(lp(n,4000),900)*np.exp(-tt*22)
def hat():
    d=0.06; tt=np.arange(int(d*SR))/SR; return hp(rng.standard_normal(len(tt)),7000)*np.exp(-tt*70)
K,C,H=kick(),clap(),hat()
for b in range(nb):
    for q in range(4):
        t=b*bar+q*beat
        if t<DROP-0.01 or t>=OUT: continue
        brk=BREAK[0]<=t<BREAK[1]
        if q in (0,2) and not brk: add(K,t,gain=0.55)
        if q in (1,3): add(C,t,gain=0.10 if not brk else 0.06)
        for e in (0,0.5):
            if not brk: add(H,t+e*beat,pan=0.25,gain=0.05 if e else 0.03)
    # 贝斯
    t0=b*bar
    if DROP-0.01<=t0<OUT or (t0<DROP and t0+bar>DROP):
        for k in range(8):
            t=t0+k*beat/2
            if t<DROP-0.01 or t>=OUT or k in (1,5): continue
            m=roots[b%4]-12+(12 if k in (3,7) else 0); d=beat/2*0.9; tt=np.arange(int(d*SR))/SR
            s=np.tanh(1.5*np.sin(2*np.pi*mtof(m)*tt))*np.minimum(1,(d-tt)/0.02)*np.minimum(1,tt/0.005)
            add(lp(s,500),t,gain=0.16 if not BREAK[0]<=t<BREAK[1] else 0.09)
# 开头上扬噪声
d=DROP; tt=np.arange(int(d*SR))/SR
sw=hp(rng.standard_normal(len(tt)),2000)*(tt/d)**3*0.06; add(sw,0)
mix=np.stack([L,R],1)
fade=np.ones(N); fi=int(0.3*SR); fo=int(2.5*SR); fade[:fi]=np.linspace(0,1,fi); fade[-fo:]=np.linspace(1,0,fo)
mix*=fade[:,None]; mix/=np.abs(mix).max()*1.12
wavfile.write("bgm.wav",SR,(mix*32767).astype(np.int16)); print("ok")
