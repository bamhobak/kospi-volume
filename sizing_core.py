# -*- coding: utf-8 -*-
"""종목당 비중 — 30시드 평균으로 잡음 제거"""
import io,sys,numpy as np,pandas as pd
A=pd.read_csv("data/rules_trades_kospi.csv",dtype={"date":str,"ticker":str})
B=pd.read_csv("data/rules_trades_kosdaq.csv",dtype={"date":str,"ticker":str})
T=pd.concat([A,B],ignore_index=True); T.columns=[c.lstrip("\ufeff") for c in T.columns]
T=T.dropna(subset=["r"]).reset_index(drop=True)
dates=sorted(T.date.unique()); DI={d:i for i,d in enumerate(dates)}
ORDER=["P2","P3","P4","D1"]; HOLD={"P2":10,"P3":20,"P4":40,"D1":20}
RI={k:i for i,k in enumerate(ORDER)}
sig=[[] for _ in dates]
for r in T.itertuples(): sig[DI[r.date]].append((RI[r.R],r.ticker,float(r.r)))
sig=[np.array([(a,c) for a,b,c in s],dtype=float) if s else None for s in sig]
TKS=[[b for a,b,c in s] for s in [ [(a,b,c) for a,b,c in x] for x in
      [[(RI[r.R],r.ticker,float(r.r)) for r in T[T.date==d].itertuples()] for d in dates]]]
def sim(size,cap,d0,d1,seed):
    rng=np.random.default_rng(seed)
    cash=100.0; peak=100.0; mdd=0.0; n=0
    amt=[];ret=[];out=[];rid=[];tks=[]
    i0=next(i for i,d in enumerate(dates) if d>=d0)
    i1=max(i for i,d in enumerate(dates) if d<=d1)
    for i in range(i0,i1+1):
        keep=[]
        for j in range(len(amt)):
            if out[j]<=i: cash+=amt[j]*(1+ret[j]/100); n+=1
            else: keep.append(j)
        amt=[amt[j] for j in keep]; ret=[ret[j] for j in keep]
        out=[out[j] for j in keep]; rid=[rid[j] for j in keep]; tks=[tks[j] for j in keep]
        eq=cash+sum(amt)
        s=sig[i]
        if s is not None and len(s):
            idx=rng.permutation(len(s))
            for j in idx:
                k=int(s[j,0]); tk=TKS[i][j]
                if size[k]<=0: continue
                if sum(1 for x in rid if x==k)>=cap[k]: continue
                if tk in tks: continue
                a=eq*size[k]/100
                if a>cash: continue
                amt.append(a);ret.append(s[j,1]);out.append(i+HOLD[ORDER[k]]);rid.append(k);tks.append(tk)
                cash-=a
        eq=cash+sum(amt); peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak*100)
    eq=cash+sum(amt[j]*(1+ret[j]/100) for j in range(len(amt)))
    return eq,mdd,n
IS=("20180101","20221231"); OS=("20230101","20260831"); YIS,YOS=5.0,3.66
def ev(size,cap,seeds=30):
    o=[]
    for s in range(seeds):
        e1,m1,_=sim(size,cap,*IS,s); e2,m2,n2=sim(size,cap,*OS,s)
        o.append((((e1/100)**(1/YIS)-1)*100,m1,((e2/100)**(1/YOS)-1)*100,m2,n2))
    o=np.array(o); return o.mean(axis=0)
