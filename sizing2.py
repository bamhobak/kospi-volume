# -*- coding: utf-8 -*-
"""종목당 투입비중 그리드 탐색 — 학습·검증 양쪽에서 평가
   계좌 100, 레버리지 없음. 규칙별 (종목당 비중, 최대 동시보유) 조합을 훑는다.
"""
import io,sys,itertools,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
A=pd.read_csv("data/rules_trades_kospi.csv",dtype={"date":str,"ticker":str})
B=pd.read_csv("data/rules_trades_kosdaq.csv",dtype={"date":str,"ticker":str})
T=pd.concat([A,B],ignore_index=True); T.columns=[c.lstrip("\ufeff") for c in T.columns]
T=T.dropna(subset=["r"]).sort_values("date").reset_index(drop=True)
dates=sorted(T.date.unique()); DI={d:i for i,d in enumerate(dates)}
ORDER=["P2","P3","P4","D1"]
BY={}
for d,gg in T.groupby("date"): BY[d]=gg
HOLD={k:int(T[T.R==k].hold.iloc[0]) for k in ORDER}
def sim(size,cap,d0,d1,seed=0):
    """size[k]=종목당 계좌 %, cap[k]=규칙별 최대 동시보유"""
    rng=np.random.default_rng(seed)
    cash=100.0; held=[]; peak=100.0; mdd=0.0; n=0
    for d in dates:
        if d<d0 or d>d1: continue
        i=DI[d]
        keep=[]
        for h in held:
            if h["out"]<=i: cash+=h["amt"]*(1+h["r"]/100); n+=1
            else: keep.append(h)
        held=keep
        eq=cash+sum(h["amt"] for h in held)
        gg=BY.get(d)
        if gg is not None:
            gg=gg.sample(frac=1,random_state=int(rng.integers(1<<30)))
            for r in gg.itertuples():
                k=r.R
                if size[k]<=0: continue
                if sum(1 for h in held if h["R"]==k)>=cap[k]: continue
                if any(h["tk"]==r.ticker for h in held): continue
                amt=eq*size[k]/100
                if amt>cash: continue
                held.append(dict(R=k,tk=r.ticker,amt=amt,r=r.r,out=i+HOLD[k])); cash-=amt
        eq=cash+sum(h["amt"] for h in held)
        peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak*100)
    eq=cash+sum(h["amt"]*(1+h["r"]/100) for h in held)
    return eq,mdd,n
IS=("20180101","20221231"); OS=("20230101","20260831")
YIS,YOS=5.0,3.66
print("## 규칙별 종목당 비중 후보 — 다른 규칙은 고정하고 하나씩 훑기\n")
BASE={"P2":10,"P3":10,"P4":8,"D1":10}
CAP={"P2":4,"P3":6,"P4":8,"D1":6}
for k in ORDER:
    print(f"\n### {k} 종목당 비중 (나머지는 기본값 고정)\n")
    print("| 비중 | 학습 연평균 | 학습 MDD | **검증 연평균** | 검증 MDD | 검증 거래수 |\n|---|---|---|---|---|---|")
    for v in (0,3,5,8,10,15,20,25):
        s=dict(BASE); s[k]=v
        e1,m1,_=sim(s,CAP,*IS,seed=1); e2,m2,n2=sim(s,CAP,*OS,seed=1)
        c1=((e1/100)**(1/YIS)-1)*100; c2=((e2/100)**(1/YOS)-1)*100
        print(f"| {v}% | {c1:+.1f}% | {m1:.0f}% | **{c2:+.1f}%** | {m2:.0f}% | {n2} |")
