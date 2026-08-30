# -*- coding: utf-8 -*-
"""최종 판정 — 고정 보유일 후보를 학습·검증 양쪽 부트스트랩으로 비교"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
rng=np.random.default_rng(99)
D=pd.read_pickle("data/bull_feat.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
g=D.groupby("ticker",sort=False)
D["ret250"]=g.close.transform(lambda x:x/x.shift(250)-1)*100
D["above20"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
dates=sorted(D.date.unique()); DI={d:i for i,d in enumerate(dates)}
lastpos=g.date.transform("max").map(DI); lastclose=g.close.transform("last"); mypos=D.date.map(DI)
HZ=[10,15,20,25,30,40,50]
for h in HZ:
    sell=g.close.shift(-h).where(~(mypos+h>lastpos), lastclose)
    D[f"n{h}"]=(sell/D.buy-1)*100-D.cost
M=(((D.fromhi>=-10)&(D.r16<120)&(D.rw1<=120)&(D.fw5>=3)&(D.fw60>=1)&(D.vol20<=3)
   &(D.sr20<=1)&(D.ret20<=10)&(D.amt20>=50)&(~D.dil)).fillna(False)
   & ~((D.above20>70)&(D.ret250>120)).fillna(False))
idx=np.where(M.values)[0]; DT=D.date.values; tick=D.ticker.values
sig={}
for i in idx: sig.setdefault(DT[i],[]).append(i)
NV={h:D[f"n{h}"].values for h in HZ}
def sim(h,slots,d0,d1,drop,r):
    cash=30_000_000;held={}
    for d in dates:
        if d<d0 or d>d1: continue
        for k in [k for k,v in held.items() if v["out"]<=DI[d]]:
            v=held.pop(k);cash+=v["amt"]*(1+v["r"]/100)
        eq=cash+sum(v["amt"] for v in held.values())
        for i in sig.get(d,[]):
            if len(held)>=slots or tick[i] in held: continue
            if r.random()<drop: continue
            v=NV[h][i]
            if not np.isfinite(v): continue
            amt=min(eq/slots,cash)
            if amt<200000: continue
            held[tick[i]]={"amt":amt,"r":v,"out":DI[d]+h};cash-=amt
    return (cash+sum(v["amt"]*(1+v["r"]/100) for v in held.values()))/30_000_000*100-100
for lab,d0s,d1,yrs in [("학습 2018~22",[d for d in dates if "20180101"<=d<="20200601"],"20221231",2.8),
                       ("검증 2023~26",[d for d in dates if "20230101"<=d<="20240601"],"20260831",3.0)]:
    res={h:[] for h in HZ}
    for _ in range(250):
        d0=d0s[rng.integers(len(d0s))];slots=int(rng.integers(3,16));drop=rng.uniform(0,0.5);s=int(rng.integers(1<<30))
        for h in HZ: res[h].append(sim(h,slots,d0,d1,drop,np.random.default_rng(s)))
    b40=np.array(res[40])
    print(f"\n## {lab} · 부트스트랩 250회 (시작월·슬롯3~15·누락0~50% 무작위)\n")
    print("| 보유 | 중앙 총수익 | 하위25% | 손실확률 | **40일 대비 우세** |\n|---|---|---|---|---|")
    for h in HZ:
        v=np.array(res[h])
        print(f"| {h}일 | **{np.median(v):+.1f}%** | {np.percentile(v,25):+.1f}% | {(v<0).mean()*100:.0f}% | {(v>b40).mean()*100:.0f}% |")
