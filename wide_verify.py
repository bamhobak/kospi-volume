# -*- coding: utf-8 -*-
"""고빈도 후보 정밀 검증 — 보유기간 5~40일 · 월단위 신뢰구간 · 기존 규칙 중복"""
import io,sys,csv,pickle,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
IND={}
for r in csv.DictReader(open("data/industry.csv",encoding="utf-8-sig")):
    k=list(r.values()); IND[k[0]]=k[-1]
HZ=[5,10,15,20,30,40]
def prep(path,amtmin):
    D=pd.read_pickle(path).sort_values(["ticker","date"]).reset_index(drop=True)
    D["up"]=D.ticker.map(IND)
    d=D[D.up.notna()].dropna(subset=["ret60"]); g=d.groupby(["date","up"]).ret60
    m=g.median(); c=g.size(); m=m[c>=5]
    D["u"]=pd.MultiIndex.from_arrays([D.date,D.up]).map(m)
    dates=sorted(D.date.unique()); DI={x:i for i,x in enumerate(dates)}
    g2=D.groupby("ticker",sort=False)
    lastpos=g2.date.transform("max").map(DI); lastclose=g2.close.transform("last"); mypos=D.date.map(DI)
    for h in HZ:
        if f"n{h}" in D.columns: continue
        sell=g2.close.shift(-h).where(~(mypos+h>lastpos),lastclose)
        D[f"n{h}"]=(sell/D.buy-1)*100-D.cost
    D["ok"]=((D.close>=1000)&(~D.dil)&(D.amt20>=amtmin)).fillna(False)
    return D
K=prep("data/kp_cap.pkl",10); Q=prep("data/kq_cap.pkl",5)
print(f"코스피 {len(K):,}행 · 코스닥 {len(Q):,}행 · 보유 {HZ}\n")
K.to_pickle("data/kp_hz.pkl"); Q.to_pickle("data/kq_hz.pkl")
rng=np.random.default_rng(11)
def ev(D,label,M,name):
    X=D[(M&D.ok).fillna(False)].copy(); X["ym"]=X.date.str[:6]
    print(f"\n### {label} — {name}  (전체 {len(X):,}건)\n")
    print("| 보유 | 학습건수 | 학습승률 | 학습평균 | 검증건수 | **검증승률** | **검증평균** | 중앙값 | PF | 하위5% | **월단위 95%** | 일당 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    best=None
    for h in HZ:
        a=X[X.y<=2022][f"n{h}"].dropna().values; b=X[X.y>=2023]
        r=b[f"n{h}"].dropna().values
        if len(r)<50: continue
        pf=r[r>0].sum()/abs(r[r<=0].sum()) if (r<=0).any() else 99
        mo=[list(x.dropna()) for _,x in b.groupby("ym")[f"n{h}"]]; mo=[x for x in mo if x]
        bs=np.array([np.mean([v for i in rng.integers(0,len(mo),len(mo)) for v in mo[i]]) for _ in range(1200)])
        lo,hi=np.percentile(bs,2.5),np.percentile(bs,97.5)
        print(f"| {h}일 | {len(a):,} | {(a>0).mean()*100:.0f}% | {a.mean():+.1f}% | {len(r):,} | **{(r>0).mean()*100:.0f}%** | **{r.mean():+.2f}%** | {np.median(r):+.2f}% | {pf:.2f} | {np.percentile(r,5):.0f}% | **{lo:+.1f}~{hi:+.1f}%** | {r.mean()/h:+.3f}% |")
    return X
# 반복 등장한 핵심 재료 + 변형
CAND_K=[("A 업종-20 + 20일선이격-10 + 공매도감소 + 회전율0.5", (K.u<=-20)&(K.dma20<=-10)&(K.srd==True)&(K.회전율>=0.5)),
        ("B 업종-20 + 20일선이격-10 + 공매도감소", (K.u<=-20)&(K.dma20<=-10)&(K.srd==True)),
        ("C 업종-20 + 20일선이격-10 + ROE≥0 + 공매도감소", (K.u<=-20)&(K.dma20<=-10)&(K.ROE>=0)&(K.srd==True)),
        ("D 업종-20 + 20일선이격-10", (K.u<=-20)&(K.dma20<=-10))]
CAND_Q=[("A PBR≤1 + 업종-20 + 공매도감소 + 20일선이격-10", (Q.PBR<=1)&(Q.u<=-20)&(Q.srd==True)&(Q.dma20<=-10)),
        ("B 업종-20 + 20일선이격-10 + 공매도감소", (Q.u<=-20)&(Q.dma20<=-10)&(Q.srd==True)),
        ("C PBR≤1 + 시총≤1000억 + 업종-20 + 공매도감소", (Q.PBR<=1)&(Q.marcap<=1000)&(Q.u<=-20)&(Q.srd==True))]
for nm,m in CAND_K: ev(K,"코스피",m.fillna(False),nm)
for nm,m in CAND_Q: ev(Q,"코스닥",m.fillna(False),nm)
