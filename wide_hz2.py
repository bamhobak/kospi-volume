# -*- coding: utf-8 -*-
"""보유기간 1~60일 전수 + 비중 축소 포트폴리오 재검증"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
HZ=[1,2,3,4,5,7,10,12,15,20,25,30,40,50,60]
K=pd.read_pickle("data/kp_hz.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
dates=sorted(K.date.unique()); DI={d:i for i,d in enumerate(dates)}
g=K.groupby("ticker",sort=False)
lastpos=g.date.transform("max").map(DI); lastclose=g.close.transform("last"); mypos=K.date.map(DI)
for h in HZ:
    if f"n{h}" in K.columns: continue
    sell=g.close.shift(-h).where(~(mypos+h>lastpos),lastclose)
    K[f"n{h}"]=(sell/K.buy-1)*100-K.cost
K.to_pickle("data/kp_hz2.pkl")
CAND={"A 회전율":(K.u<=-20)&(K.dma20<=-10)&(K.srd==True)&(K.회전율>=0.5),
      "B 최소":(K.u<=-20)&(K.dma20<=-10)&(K.srd==True),
      "C ROE":(K.u<=-20)&(K.dma20<=-10)&(K.ROE>=0)&(K.srd==True)}
rng=np.random.default_rng(21)
for nm,m in CAND.items():
    X=K[(m&K.ok).fillna(False)].copy(); X["ym"]=X.date.str[:6]
    print(f"\n## {nm} — 보유기간 전수 (검증 2023~26, {len(X):,}건)\n")
    print("| 보유 | 학습승률 | 학습평균 | **검증승률** | **검증평균** | 중앙값 | PF | 하위5% | **월단위 95%** | **일당** |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for h in HZ:
        a=X[X.y<=2022][f"n{h}"].dropna().values; b=X[X.y>=2023]
        r=b[f"n{h}"].dropna().values
        if len(r)<50: continue
        pf=r[r>0].sum()/abs(r[r<=0].sum()) if (r<=0).any() else 99
        mo=[list(x.dropna()) for _,x in b.groupby("ym")[f"n{h}"]]; mo=[x for x in mo if x]
        bs=np.array([np.mean([v for i in rng.integers(0,len(mo),len(mo)) for v in mo[i]]) for _ in range(1200)])
        lo,hi=np.percentile(bs,2.5),np.percentile(bs,97.5)
        mark="**" if lo>0 else ""
        print(f"| {h}일 | {(a>0).mean()*100:.0f}% | {a.mean():+.1f}% | {(r>0).mean()*100:.0f}% | **{r.mean():+.2f}%** | {np.median(r):+.2f}% | {pf:.2f} | {np.percentile(r,5):.0f}% | {mark}{lo:+.1f}~{hi:+.1f}%{mark} | {r.mean()/h:+.3f}% |")
