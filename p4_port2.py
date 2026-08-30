# -*- coding: utf-8 -*-
"""자금배분 방식·손절·슬롯수를 바꿔가며 결론이 유지되는지 검증"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/bull_feat.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
g=D.groupby("ticker",sort=False)
D["ret250"]=g.close.transform(lambda x:x/x.shift(250)-1)*100
D["above20"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
D["vavg20"]=g.volume.transform(lambda x:x.rolling(20).mean())
M=(((D.fromhi>=-10)&(D.r16<120)&(D.rw1<=120)&(D.fw5>=3)&(D.fw60>=1)&(D.vol20<=3)
   &(D.sr20<=1)&(D.ret20<=10)&(D.amt20>=50)&(~D.dil)).fillna(False)
   & ~((D.above20>70)&(D.ret250>120)).fillna(False))
dates=sorted(D.date.unique()); DI={d:i for i,d in enumerate(dates)}
tick=D.ticker.values;C=D.close.values;OP=D.open.values;LO=D.low.values
VOL=D.volume.values;VA=D.vavg20.values;BUY=D.buy.values;COST=D.cost.values;DT=D.date.values
paths={}
for i in np.where(M.values)[0]:
    b=BUY[i]
    if not np.isfinite(b): continue
    j=i+1;t=tick[i];p=[]
    while j<len(D) and tick[j]==t and len(p)<60:
        p.append((C[j],VOL[j],VA[j],OP[j+1] if (j+1<len(D) and tick[j+1]==t) else np.nan,LO[j]));j+=1
    if len(p)>=5: paths[i]=(b,COST[i],np.array(p,dtype=float))
def mk(kind,stop=None,**o):
    out={}
    for i,(b,cst,p) in paths.items():
        n=min(o.get("cap",o.get("n",40)),len(p)); r=None
        for k in range(n):
            if stop and p[k,4]<=b*(1-stop/100): r=(-stop-cst,k+1); break
            if kind=="v" and np.isfinite(p[k,2]) and p[k,2]>0 and p[k,1]>=o["mult"]*p[k,2]:
                px=p[k,3] if np.isfinite(p[k,3]) else p[k,0]; r=((px/b-1)*100-cst,k+2); break
        if r is None: r=((p[n-1,0]/b-1)*100-cst,n)
        out[i]=r
    return out
sig={}
for i in paths: sig.setdefault(DT[i],[]).append(i)
def sim(tab,slots,seed,d0,sizing):
    cash=seed;held={};peak=seed;mdd=0;done=[]
    for d in dates:
        if d<d0: continue
        for k in [k for k,v in held.items() if v["out"]<=DI[d]]:
            v=held.pop(k);cash+=v["amt"]*(1+v["r"]/100);done.append(v["r"])
        eq=cash+sum(v["amt"] for v in held.values())
        for i in sig.get(d,[]):
            if len(held)>=slots or tick[i] in held: continue
            amt=(eq/slots) if sizing=="equal" else cash/max(slots-len(held),1)
            amt=min(amt,cash)
            if amt<200000: continue
            r,dd=tab[i];held[tick[i]]={"amt":amt,"r":r,"out":DI[d]+dd};cash-=amt
        eq=cash+sum(v["amt"] for v in held.values());peak=max(peak,eq);mdd=max(mdd,(peak-eq)/peak*100)
    eq=cash+sum(v["amt"]*(1+v["r"]/100) for v in held.values())
    return eq,len(done),mdd
SEED=30_000_000
R=[("고정 15일",mk("fixed",n=15)),("고정 20일",mk("fixed",n=20)),("고정 40일",mk("fixed",n=40)),
   ("거래량2.5배/40일",mk("v",mult=2.5,cap=40)),("거래량3배/40일",mk("v",mult=3,cap=40)),
   ("거래량3배/40일+손절15%",mk("v",mult=3,cap=40,stop=15)),
   ("고정40일+손절15%",mk("fixed",n=40,stop=15))]
for sizing,lab in (("equal","자산 균등배분 (자산/슬롯)"),("greedy","빈슬롯 현금집중")):
    print(f"\n## {lab} · 검증기간(2023~26)\n")
    print("| 청산규칙 | 3종목 | 5종목 | 10종목 | 20종목 |\n|---|---|---|---|---|")
    for nm,tab in R:
        cells=[]
        for s in (3,5,10,20):
            eq,n,mdd=sim(tab,s,SEED,"20230101",sizing)
            cells.append(f"**{(eq/SEED-1)*100:+.1f}%**")
        print(f"| {nm} | "+" | ".join(cells)+" |")
print("\n## 연도별 자산 증감 — 거래량3배/40일 vs 고정40일 (10종목·균등배분)\n")
print("| 규칙 | "+" | ".join(str(y) for y in range(2018,2027))+" |\n|---|"+"---|"*9)
for nm,tab in [("고정 40일",mk("fixed",n=40)),("거래량3배/40일",mk("v",mult=3,cap=40))]:
    cells=[]
    for y in range(2018,2027):
        eq,n,_=sim(tab,10,SEED,f"{y}0101",  "equal")
        # 해당 연도만: 시작 자금 대비 그 해 말까지 (근사) — 연도 필터로 재계산
        sub={i:v for i,v in tab.items() if DT[i][:4]==str(y)}
        if not sub: cells.append("-"); continue
        rs=[v[0] for v in sub.values()]
        cells.append(f"{np.mean(rs):+.1f}%<br>{len(rs)}건")
    print(f"| {nm} | "+" | ".join(cells)+" |")
