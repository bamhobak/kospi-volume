# -*- coding: utf-8 -*-
"""강화안의 실제 계좌 효과 — 네 규칙 함께 · 확정 비중 · 60시드"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/bull_feat.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
g=D.groupby("ticker",sort=False)
D["ret250"]=g.close.transform(lambda x:x/x.shift(250)-1)*100
D["above20"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
BASE=(((D.fromhi>=-10)&(D.r16<120)&(D.rw1<=120)&(D.fw5>=3)&(D.fw60>=1)&(D.vol20<=3)
      &(D.sr20<=1)&(D.ret20<=10)&(D.amt20>=50)&(~D.dil)).fillna(False)
      & ~((D.above20>70)&(D.ret250>120)).fillna(False))
X=D[BASE]
VAR={"현행":X,
     "A 강화":X[((X.vol20<=2)&(X.sr20<=0.5)&(X.ret20<=5)).fillna(False)],
     "C 더 강화":X[((X.vol20<=2)&(X.sr20<=0.5)&(X.ret20<=5)&(X.amt20>=200)).fillna(False)]}
# 다른 규칙 거래
A=pd.read_csv("data/rules_trades_kospi.csv",dtype={"date":str,"ticker":str})
B=pd.read_csv("data/rules_trades_kosdaq.csv",dtype={"date":str,"ticker":str})
for x in (A,B): x.columns=[c.lstrip("\ufeff") for c in x.columns]
K=pd.read_pickle("data/kd_risk.pkl").set_index(["date","ticker"])[["close"]]
B=B.join(K,on=["date","ticker"]); B=B[B.close.fillna(0)>=1000]
OTH=pd.concat([A[A.R.isin(["P2","P3"])],B],ignore_index=True)[["R","date","ticker","y","r","hold"]]
SIZE={"P1":12,"P2":15,"P3":5,"D1":5}; CAP={"P1":7,"P2":2,"P3":3,"D1":3}
HOLD={"P1":40,"P2":10,"P3":20,"D1":5}
HOLD={"P1":40,"P2":10,"P3":20,"D1":20}
print("## 계좌 100 · 확정 비중 · 60시드 평균\n")
print("| P1 안 | P1 건수 | 학습 연평균 | 학습MDD | **검증 연평균** | 검증MDD | 검증 손실확률 | 평균 보유종목 |")
print("|---|---|---|---|---|---|---|---|")
for nm,P in VAR.items():
    T=pd.concat([P.assign(R="P1",hold=40)[["R","date","ticker","y","n40","hold"]].rename(columns={"n40":"r"}),OTH],ignore_index=True)
    T=T.dropna(subset=["r"])
    dates=sorted(T.date.unique()); DI={d:i for i,d in enumerate(dates)}
    sig={}
    for r in T.itertuples(): sig.setdefault(r.date,[]).append((r.R,r.ticker,float(r.r)))
    def sim(d0,d1,seed):
        rng=np.random.default_rng(seed); cash=100.0;peak=100.0;mdd=0.0
        held=[];cnts=[]
        i0=next(i for i,d in enumerate(dates) if d>=d0); i1=max(i for i,d in enumerate(dates) if d<=d1)
        for i in range(i0,i1+1):
            keep=[]
            for h in held:
                if h["out"]<=i: cash+=h["amt"]*(1+h["r"]/100)
                else: keep.append(h)
            held=keep; eq=cash+sum(h["amt"] for h in held)
            s=sig.get(dates[i],[])
            for j in rng.permutation(len(s)):
                R,tk,rr=s[j]
                if sum(1 for h in held if h["R"]==R)>=CAP[R]: continue
                if any(h["tk"]==tk for h in held): continue
                a=eq*SIZE[R]/100
                if a>cash: continue
                held.append(dict(R=R,tk=tk,amt=a,r=rr,out=i+HOLD[R])); cash-=a
            eq=cash+sum(h["amt"] for h in held); peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak*100)
            cnts.append(len(held))
        eq=cash+sum(h["amt"]*(1+h["r"]/100) for h in held)
        return eq,mdd,np.mean(cnts)
    o=[]
    for s in range(60):
        e1,m1,_=sim("20180101","20221231",s); e2,m2,c2=sim("20230101","20260831",s)
        o.append(((e1/100)**(1/5)*100-100,m1,((e2/100)**(1/3.66))*100-100,m2,c2))
    o=np.array(o)
    print(f"| {nm} | {len(P):,} | {o[:,0].mean():+.1f}% | {o[:,1].mean():.0f}% | **{o[:,2].mean():+.1f}%** | "
          f"{o[:,3].mean():.0f}% | {(o[:,2]<0).mean()*100:.0f}% | {o[:,4].mean():.1f}종목 |")
