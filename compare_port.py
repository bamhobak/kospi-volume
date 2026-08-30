# -*- coding: utf-8 -*-
"""계좌 100 고정 시 원래 vs 강화 — 60시드. 그리고 표본 신뢰구간."""
import io,sys,pickle,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
TR=pickle.load(open("data/cmp_trades.pkl","rb"))
SIZE={"P1":12,"P2":15,"P3":5,"D1":5}; CAP={"P1":7,"P2":2,"P3":3,"D1":3}
def sim(T,d0,d1,seed,size,cap):
    rng=np.random.default_rng(seed)
    dates=sorted(T.date.unique()); DI={d:i for i,d in enumerate(dates)}
    sig={}
    for r in T.itertuples(): sig.setdefault(r.date,[]).append((r.R,r.ticker,float(r.r),int(r.hold)))
    cash=100.0;held=[];peak=100.0;mdd=0.0;n=0
    i0=next(i for i,d in enumerate(dates) if d>=d0); i1=max(i for i,d in enumerate(dates) if d<=d1)
    for i in range(i0,i1+1):
        keep=[]
        for h in held:
            if h["out"]<=i: cash+=h["amt"]*(1+h["r"]/100); n+=1
            else: keep.append(h)
        held=keep; eq=cash+sum(h["amt"] for h in held)
        s=sig.get(dates[i],[])
        for j in rng.permutation(len(s)):
            R,tk,rr,hd=s[j]
            if sum(1 for h in held if h["R"]==R)>=cap[R]: continue
            if any(h["tk"]==tk for h in held): continue
            a=eq*size[R]/100
            if a>cash: continue
            held.append(dict(R=R,tk=tk,amt=a,r=rr,out=i+hd)); cash-=a
        eq=cash+sum(h["amt"] for h in held); peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak*100)
    eq=cash+sum(h["amt"]*(1+h["r"]/100) for h in held)
    return eq,mdd,n
print("## 계좌 100 고정 · 60시드 평균\n")
print("| | 학습 연평균 | 학습MDD | **검증 연평균** | 검증MDD | 검증 손실확률 | 검증 거래수 |")
print("|---|---|---|---|---|---|---|")
OUT={}
for ver in ("원래","강화"):
    T=TR[ver]; o=[]
    for s in range(60):
        e1,m1,_=sim(T,"20180101","20221231",s,SIZE,CAP)
        e2,m2,n2=sim(T,"20230101","20260831",s,SIZE,CAP)
        o.append((((e1/100)**(1/5)-1)*100,m1,((e2/100)**(1/3.66)-1)*100,m2,n2))
    o=np.array(o); OUT[ver]=o
    print(f"| {ver} | {o[:,0].mean():+.1f}% | {o[:,1].mean():.0f}% | **{o[:,2].mean():+.1f}%** | {o[:,3].mean():.0f}% | {(o[:,2]<0).mean()*100:.0f}% | {o[:,4].mean():.0f}건 |")
print(f"\n강화가 검증에서 원래를 이긴 비율: **{(OUT['강화'][:,2]>OUT['원래'][:,2]).mean()*100:.0f}%** (60시드 중)")
print("\n## 규칙별 단독 — 계좌 100 전부를 그 규칙에만 (검증)\n")
print("| 규칙 | 원래 연평균 | 원래MDD | 강화 연평균 | 강화MDD |\n|---|---|---|---|---|")
for nm in ("P1","P2","P3","D1"):
    row=[]
    for ver in ("원래","강화"):
        T=TR[ver]; T=T[T.R==nm]
        if not len(T): row+=["—","—"]; continue
        o=[sim(T,"20230101","20260831",s,SIZE,{**CAP,nm:CAP[nm]}) for s in range(40)]
        o=np.array([(((e/100)**(1/3.66)-1)*100,m) for e,m,_ in o])
        row+=[f"{o[:,0].mean():+.1f}%",f"{o[:,1].mean():.0f}%"]
    print(f"| {nm} | "+" | ".join(row)+" |")
print("\n## 표본 신뢰도 — 검증 건수가 적은 규칙은 얼마나 믿을 수 있나 (부트스트랩 2000회)\n")
print("| 규칙 | 건수 | 관측 건당 | **95% 신뢰구간** | 실제로 (+)일 확률 |\n|---|---|---|---|---|")
rng=np.random.default_rng(0)
for ver in ("원래","강화"):
    for nm in ("P1","P2","P3","D1"):
        T=TR[ver]; r=T[(T.R==nm)&(T.y>=2023)].r.values
        if len(r)<5: continue
        bs=np.array([rng.choice(r,len(r),replace=True).mean() for _ in range(2000)])
        print(f"| {nm} ({ver}) | {len(r)} | {r.mean():+.2f}% | {np.percentile(bs,2.5):+.1f}% ~ {np.percentile(bs,97.5):+.1f}% | {(bs>0).mean()*100:.0f}% |")
