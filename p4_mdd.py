# -*- coding: utf-8 -*-
"""P4 + 60일 최대낙폭 ≤ -40% 넣을지 비교 (실거래 기준·전 체크리스트)"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
K=pd.read_pickle("data/kp_hz2.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
g=K.groupby("ticker",sort=False)
K["hi60"]=g.close.transform(lambda x:x.rolling(60,min_periods=30).max())
K["dd"]=(K.close/K.hi60-1)*100
K["mdd60"]=g["dd"].transform(lambda x:x.rolling(60,min_periods=30).min())
K["above20r"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(60,min_periods=30).mean())*100
for h in (3,5,10,20):
    K[f"lo{h}"]=g.low.shift(-1).rolling(h,min_periods=1).min().shift(-(h-1))
dates=sorted(K.date.unique()); DI={d:i for i,d in enumerate(dates)}
K["di"]=K.date.map(DI)
BASE=((K.u<=-20)&(K.dma20<=-10)&(K.srd==True)&K.ok).fillna(False)
rng=np.random.default_rng(555)
def trades(M,h,stop=15):
    X=K[M].copy()
    r=X[f"n{h}"].values.astype(float)
    hit=((X[f"lo{h}"]/X.buy-1)*100<=-stop).values
    r=np.where(hit,-stop-X.cost.values,r)
    X["r"]=r; X=X.dropna(subset=["r"])
    keep=[];last={}
    for row in X.sort_values("di").itertuples():
        if row.ticker in last and row.di-last[row.ticker]<h: continue
        last[row.ticker]=row.di; keep.append(row.Index)
    return X.loc[keep]
def stat(Y,lab,h):
    Y=Y.copy(); Y["ym"]=Y.date.str[:6]
    a=Y[Y.y<=2022].r.values; b=Y[Y.y>=2023]; r=b.r.values
    if len(r)<30: return
    pf=r[r>0].sum()/abs(r[r<=0].sum()) if (r<=0).any() else 99
    mo=[list(x) for _,x in b.groupby("ym").r]; mo=[x for x in mo if x]
    bs=np.array([np.mean([v for i in rng.integers(0,len(mo),len(mo)) for v in mo[i]]) for _ in range(1500)])
    lo,hi=np.percentile(bs,2.5),np.percentile(bs,97.5)
    mk="**" if lo>0 else ""
    print(f"| {lab} | {len(Y):,} | {a.mean():+.2f}% | {len(r):,} | {(r>0).mean()*100:.0f}% | **{r.mean():+.2f}%** | {np.median(r):+.2f}% | {pf:.2f} | {np.percentile(r,5):.1f}% | {mk}{lo:+.2f}~{hi:+.2f}%{mk} |")
print("## 1) 보유기간별 — 넣기 전 vs 후\n")
for h in (3,5,10,20):
    print(f"\n**{h}일 보유**\n")
    print("| 안 | 실거래 | 학습 | 검증건수 | 승률 | **검증평균** | 중앙값 | PF | 하위5% | 월단위 95% |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    stat(trades(BASE,h),"현행",h)
    stat(trades(BASE&(K.mdd60<=-40),h),"+ 최대낙폭 ≤ -40%",h)
    stat(trades(BASE&(K.mdd60<=-30),h),"+ 최대낙폭 ≤ -30%",h)
    stat(trades(BASE&(K.mdd60<=-50),h),"+ 최대낙폭 ≤ -50%",h)
Y0=trades(BASE,5); Y1=trades(BASE&(K.mdd60<=-40),5)
print("\n## 2) 연도별 (5일 보유, 실거래)\n")
YS=list(range(2018,2027))
print("| 안 | "+" | ".join(str(y) for y in YS)+" |\n|---|"+"---|"*len(YS))
for lab,Y in (("현행",Y0),("낙폭 -40%",Y1)):
    c=[]
    for y in YS:
        s=Y[Y.y==y]
        c.append(f"{s.r.mean():+.1f}%<br>{len(s)}건" if len(s)>=3 else (f"{len(s)}건" if len(s) else "—"))
    print(f"| {lab} | "+" | ".join(c)+" |")
print("\n## 3) 기존 조건과 중복인가 (업종 -20% 와 낙폭 -40% 의 관계)\n")
X=K[BASE]
print(f"- P4 신호의 60일 최대낙폭 분포: 중앙 {X.mdd60.median():.0f}% · 25%분위 {X.mdd60.quantile(.25):.0f}% · 75%분위 {X.mdd60.quantile(.75):.0f}%")
print(f"- 업종 60일과 종목 최대낙폭 상관: {X[['u','mdd60']].corr().iloc[0,1]:+.3f}")
print(f"- 낙폭 -40% 이하 비중: {(X.mdd60<=-40).mean()*100:.0f}%")
print("\n## 4) 쏠림·표본\n")
for lab,Y in (("현행",Y0),("낙폭 -40%",Y1)):
    Y=Y.copy(); Y["ym"]=Y.date.str[:6]; V=Y[Y.y>=2023]
    top=Y.groupby("ym").size().sort_values(ascending=False).head(5)
    print(f"- {lab}: 전체 {len(Y):,}건 · 고유종목 {Y.ticker.nunique()} · 신호 난 달 {Y.ym.nunique()}/104 · "
          f"검증 {len(V):,}건({V.ym.nunique()}/44개월) · 상위5개월 {top.sum()}건({top.sum()/len(Y)*100:.0f}%) · 2020년 {len(Y[Y.y==2020])/len(Y)*100:.0f}%")
print(f"\n- 폐지종목 신호: 현행 {int((Y0.grp=='폐지').sum())}건 · 낙폭조건 {int((Y1.grp=='폐지').sum())}건")
