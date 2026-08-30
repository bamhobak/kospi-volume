# -*- coding: utf-8 -*-
"""학습기간 부트스트랩 + 실제 보유일 분포"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
rng=np.random.default_rng(7)
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
BUY=D.buy.values;COST=D.cost.values;DT=D.date.values;Y=D.y.values
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
T40=mk("fixed",n=40); TV=mk("v",mult=3,cap=40); TV30=mk("v",mult=3,cap=30)
sig={}
for i in paths: sig.setdefault(DT[i],[]).append(i)
def sim(tab,slots,d0,d1,drop,r):
    cash=30_000_000;held={}
    for d in dates:
        if d<d0 or d>d1: continue
        for k in [k for k,v in held.items() if v["out"]<=DI[d]]:
            v=held.pop(k);cash+=v["amt"]*(1+v["r"]/100)
        eq=cash+sum(v["amt"] for v in held.values())
        for i in sig.get(d,[]):
            if len(held)>=slots or tick[i] in held: continue
            if r.random()<drop: continue
            amt=min(eq/slots,cash)
            if amt<200000: continue
            rr,dd=tab[i];held[tick[i]]={"amt":amt,"r":rr,"out":DI[d]+dd};cash-=amt
    return (cash+sum(v["amt"]*(1+v["r"]/100) for v in held.values()))/30_000_000*100-100
for lab,d0s,d1 in [("학습기간(2018~22)",[d for d in dates if "20180101"<=d<="20200601"],"20221231"),
                   ("검증기간(2023~26)",[d for d in dates if "20230101"<=d<="20240601"],"20260831")]:
    A=[];B=[];Cc=[]
    for _ in range(200):
        d0=d0s[rng.integers(len(d0s))];slots=int(rng.integers(3,16));drop=rng.uniform(0,0.5)
        s=int(rng.integers(1<<30))
        A.append(sim(T40,slots,d0,d1,drop,np.random.default_rng(s)))
        B.append(sim(TV,slots,d0,d1,drop,np.random.default_rng(s)))
        Cc.append(sim(TV30,slots,d0,d1,drop,np.random.default_rng(s)))
    A,B,Cc=map(np.array,(A,B,Cc))
    print(f"\n## {lab} 부트스트랩 200회 (같은 난수 = 같은 신호집합)\n")
    print(f"| 규칙 | 중앙값 | 하위25% | 손실확률 | 고정40일 우세 |\n|---|---|---|---|---|")
    print(f"| 고정 40일 | **{np.median(A):+.1f}%** | {np.percentile(A,25):+.1f}% | {(A<0).mean()*100:.0f}% | — |")
    print(f"| 거래량3배/40일 | **{np.median(B):+.1f}%** | {np.percentile(B,25):+.1f}% | {(B<0).mean()*100:.0f}% | **{(B>A).mean()*100:.0f}%** |")
    print(f"| 거래량3배/30일 | **{np.median(Cc):+.1f}%** | {np.percentile(Cc,25):+.1f}% | {(Cc<0).mean()*100:.0f}% | **{(Cc>A).mean()*100:.0f}%** |")
print("\n## 실제 보유일 분포 — 거래량3배/40일\n")
d=np.array([v[1] for v in TV.values()])
print(f"- 중앙값 **{np.median(d):.0f}일** · 평균 {d.mean():.0f}일")
print(f"- 10일 이내 청산 {(d<=10).mean()*100:.0f}% · 20일 이내 {(d<=20).mean()*100:.0f}% · 30일 이내 {(d<=30).mean()*100:.0f}% · 40일 만기 {(d>=40).mean()*100:.0f}%")
print("\n```")
for lo,hi in [(1,5),(6,10),(11,15),(16,20),(21,25),(26,30),(31,35),(36,41)]:
    n=((d>=lo)&(d<=hi)).sum()
    print(f"{lo:>2}~{hi:>2}일  {n:>4}건 {'█'*int(n/len(d)*90)}")
print("```")
