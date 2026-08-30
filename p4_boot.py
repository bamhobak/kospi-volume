# -*- coding: utf-8 -*-
"""부트스트랩 — 청산규칙 우위가 특정 경로의 운인지 검정.
   시작월·슬롯수·신호 누락률을 무작위로 바꿔 300회 반복하고 분포를 비교한다.
"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
rng=np.random.default_rng(20260831)
D=pd.read_pickle("data/bull_feat.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
g=D.groupby("ticker",sort=False)
D["ret250"]=g.close.transform(lambda x:x/x.shift(250)-1)*100
D["above20"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
D["vavg20"]=g.volume.transform(lambda x:x.rolling(20).mean())
M=(((D.fromhi>=-10)&(D.r16<120)&(D.rw1<=120)&(D.fw5>=3)&(D.fw60>=1)&(D.vol20<=3)
   &(D.sr20<=1)&(D.ret20<=10)&(D.amt20>=50)&(~D.dil)).fillna(False)
   & ~((D.above20>70)&(D.ret250>120)).fillna(False))
dates=sorted(D.date.unique()); DI={d:i for i,d in enumerate(dates)}
tick=D.ticker.values;C=D.close.values;OP=D.open.values;VOL=D.volume.values;VA=D.vavg20.values
BUY=D.buy.values;COST=D.cost.values;DT=D.date.values
paths={}
for i in np.where(M.values)[0]:
    b=BUY[i]
    if not np.isfinite(b): continue
    j=i+1;t=tick[i];p=[]
    while j<len(D) and tick[j]==t and len(p)<60:
        p.append((C[j],VOL[j],VA[j],OP[j+1] if (j+1<len(D) and tick[j+1]==t) else np.nan));j+=1
    if len(p)>=5: paths[i]=(b,COST[i],np.array(p,dtype=float))
def mk(kind,**o):
    out={}
    for i,(b,cst,p) in paths.items():
        n=min(o.get("cap",o.get("n",40)),len(p));r=None
        if kind=="v":
            for k in range(n):
                if np.isfinite(p[k,2]) and p[k,2]>0 and p[k,1]>=o["mult"]*p[k,2]:
                    px=p[k,3] if np.isfinite(p[k,3]) else p[k,0];r=((px/b-1)*100-cst,k+2);break
        if r is None: r=((p[n-1,0]/b-1)*100-cst,n)
        out[i]=r
    return out
TABS={"고정 15일":mk("fixed",n=15),"고정 20일":mk("fixed",n=20),"고정 30일":mk("fixed",n=30),
      "고정 40일":mk("fixed",n=40),"거래량2.5배/40":mk("v",mult=2.5,cap=40),
      "거래량3배/40":mk("v",mult=3,cap=40),"거래량3배/30":mk("v",mult=3,cap=30)}
sig={}
for i in paths: sig.setdefault(DT[i],[]).append(i)
def sim(tab,slots,d0,drop,seed=30_000_000,r=None):
    cash=seed;held={}
    for d in dates:
        if d<d0: continue
        for k in [k for k,v in held.items() if v["out"]<=DI[d]]:
            v=held.pop(k);cash+=v["amt"]*(1+v["r"]/100)
        eq=cash+sum(v["amt"] for v in held.values())
        for i in sig.get(d,[]):
            if len(held)>=slots or tick[i] in held: continue
            if r is not None and r.random()<drop: continue          # 신호 누락
            amt=min(eq/slots,cash)
            if amt<200000: continue
            rr,dd=tab[i];held[tick[i]]={"amt":amt,"r":rr,"out":DI[d]+dd};cash-=amt
    return cash+sum(v["amt"]*(1+v["r"]/100) for v in held.values())
N=300; SEED=30_000_000
starts=[d for d in dates if "20230101"<=d<="20240601"]
out={k:[] for k in TABS}
for _ in range(N):
    d0=starts[rng.integers(len(starts))]; slots=int(rng.integers(3,16)); drop=rng.uniform(0,0.5)
    r=np.random.default_rng(rng.integers(1<<30))
    for k,tab in TABS.items():
        out[k].append((sim(tab,slots,d0,drop,SEED,np.random.default_rng(hash((d0,slots,int(drop*1e6)))%(1<<31)))/SEED-1)*100)
print(f"## 부트스트랩 {N}회 — 시작월·슬롯(3~15)·신호누락(0~50%) 무작위, 검증기간\n")
print("| 청산규칙 | 중앙값 | 평균 | 하위25% | 상위25% | 손실 확률 | 고정40일 대비 우세 |\n|---|---|---|---|---|---|---|")
base=np.array(out["고정 40일"])
for k in TABS:
    v=np.array(out[k])
    win=(v>base).mean()*100
    print(f"| {k} | **{np.median(v):+.1f}%** | {v.mean():+.1f}% | {np.percentile(v,25):+.1f}% | {np.percentile(v,75):+.1f}% | {(v<0).mean()*100:.0f}% | {win:.0f}% |")
print(f"\n거래량3배/40 이 고정40일을 이긴 비율: **{(np.array(out['거래량3배/40'])>base).mean()*100:.0f}%** ({N}회 중)")
d=np.array(out["거래량3배/40"])-base
print(f"차이 분포: 중앙값 {np.median(d):+.1f}%p · 5%분위 {np.percentile(d,5):+.1f}%p · 95%분위 {np.percentile(d,95):+.1f}%p")
