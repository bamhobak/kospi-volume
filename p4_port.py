# -*- coding: utf-8 -*-
"""보유기간 재검토 3 — 자본 한정 포트폴리오 시뮬
   같은 신호·같은 자금으로 청산규칙만 바꿔 최종 자산을 비교한다.
   짧게 끊으면 회전이 빨라 더 많은 신호를 잡을 수 있다 — 그게 실제로 돈이 되는가?
"""
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
tick=D.ticker.values; C=D.close.values; OP=D.open.values; VOL=D.volume.values; VA=D.vavg20.values
BUY=D.buy.values; COST=D.cost.values; DT=D.date.values
idx=np.where(M.values)[0]
TR={}   # 신호 -> (수익%, 보유일) per 규칙
paths={}
for i in idx:
    b=BUY[i]
    if not np.isfinite(b): continue
    j=i+1; t=tick[i]; p=[]
    while j<len(D) and tick[j]==t and len(p)<60:
        p.append((C[j],VOL[j],VA[j],OP[j+1] if (j+1<len(D) and tick[j+1]==t) else np.nan)); j+=1
    if len(p)>=5: paths[i]=(b,COST[i],np.array(p,dtype=float))
def mk(kind,**o):
    out={}
    for i,(b,cst,p) in paths.items():
        if kind=="fixed":
            k=min(o["n"],len(p))-1; out[i]=((p[k,0]/b-1)*100-cst,k+1)
        else:
            n=min(o["cap"],len(p)); r=None
            for k in range(n):
                if np.isfinite(p[k,2]) and p[k,2]>0 and p[k,1]>=o["mult"]*p[k,2]:
                    px=p[k,3] if np.isfinite(p[k,3]) else p[k,0]
                    r=((px/b-1)*100-cst,k+2); break
            if r is None: r=((p[n-1,0]/b-1)*100-cst,n)
            out[i]=r
    return out
RULES=[("고정 10일",mk("fixed",n=10)),("고정 15일",mk("fixed",n=15)),("고정 20일",mk("fixed",n=20)),
       ("고정 30일",mk("fixed",n=30)),("고정 40일",mk("fixed",n=40)),
       ("거래량2배/40일",mk("v",mult=2,cap=40)),("거래량2배/30일",mk("v",mult=2,cap=30)),
       ("거래량2.5배/40일",mk("v",mult=2.5,cap=40)),("거래량3배/40일",mk("v",mult=3,cap=40)),
       ("거래량3배/30일",mk("v",mult=3,cap=30))]
sig={}
for i in paths: sig.setdefault(DT[i],[]).append(i)
def sim(tab,slots,seed,d0):
    cash=seed; held={}; eq=seed; peak=seed; mdd=0; done=[]
    for d in dates:
        if d<d0: continue
        for key in [k for k,v in held.items() if v["out"]<=DI[d]]:
            v=held.pop(key); cash+=v["amt"]*(1+v["r"]/100); done.append(v["r"])
        for i in sorted(sig.get(d,[]),key=lambda i:-COST[i]):
            if len(held)>=slots or tick[i] in held: continue
            r,dd=tab[i]
            amt=cash/max(slots-len(held),1)
            if amt<200000: continue
            held[tick[i]]={"amt":amt,"r":r,"out":DI[d]+dd}; cash-=amt
        eq=cash+sum(v["amt"] for v in held.values()); peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak*100)
    eq=cash+sum(v["amt"]*(1+v["r"]/100) for v in held.values())
    return eq,len(done),mdd
SEED=30_000_000
for slots,lab in ((5,"5종목"),(10,"10종목")):
    print(f"\n## 최대 동시보유 {lab} · 자금 3,000만원 · 검증기간(2023~26, 3.7년)\n")
    print("| 청산규칙 | 거래수 | 최종자산 | **총수익** | 연평균 | 최대낙폭 |\n|---|---|---|---|---|---|")
    rows=[]
    for nm,tab in RULES:
        eq,n,mdd=sim(tab,slots,SEED,"20230101")
        tot=(eq/SEED-1)*100; cagr=((eq/SEED)**(1/3.66)-1)*100
        rows.append((nm,n,eq,tot,cagr,mdd))
    for nm,n,eq,tot,cagr,mdd in rows:
        print(f"| {nm} | {n} | {eq/1e4:,.0f}만 | **{tot:+.1f}%** | {cagr:+.1f}% | {mdd:.1f}% |")
print("\n## 전체기간(2018~26, 8.7년) · 최대 10종목\n")
print("| 청산규칙 | 거래수 | 최종자산 | **총수익** | 연평균 | 최대낙폭 |\n|---|---|---|---|---|---|")
for nm,tab in RULES:
    eq,n,mdd=sim(tab,10,SEED,"20180101")
    print(f"| {nm} | {n} | {eq/1e4:,.0f}만 | **{(eq/SEED-1)*100:+.1f}%** | {((eq/SEED)**(1/8.7)-1)*100:+.1f}% | {mdd:.1f}% |")
