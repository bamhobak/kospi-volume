# -*- coding: utf-8 -*-
"""대차잔고 감소 + 공매도 증가 조합 실측.
lend20/lend250 (대차잔고 20일평균 / 1년평균), sh20/sh250 (공매도 비중 20일평균 / 1년평균).
주의: 대차잔고는 2021-04 부터라 250일 평균이 서는 시점이 2022-04 → 학습구간이 9개월뿐.
"""
import sqlite3, warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from techlib import *
c=sqlite3.connect(f"file:{BASE}/data/toss.db?mode=ro",uri=True)
L=pd.read_sql("select date,ticker,bal_qty from lending where bal_qty is not null",c)
S=pd.read_sql("select date,ticker,vol_rate from short where vol_rate is not null",c); c.close()
X=L.merge(S,on=["date","ticker"],how="outer").sort_values(["ticker","date"])
gX=X.groupby("ticker",sort=False)
X["lend20"]=gX.bal_qty.transform(lambda s: s.rolling(20,min_periods=15).mean())
X["lend250"]=gX.bal_qty.transform(lambda s: s.rolling(250,min_periods=200).mean())
X["sh20"]=gX.vol_rate.transform(lambda s: s.rolling(20,min_periods=15).mean())
X["sh250"]=gX.vol_rate.transform(lambda s: s.rolling(250,min_periods=200).mean())
X["lr"]=X.lend20/X.lend250.replace(0,np.nan)
X["sr"]=X.sh20/X.sh250.replace(0,np.nan)
n0=len(A); T=A.merge(X[["date","ticker","lr","sr","bal_qty","vol_rate"]],on=["ticker","date"],how="left"); assert len(T)==n0
for c2 in ("lr","sr","bal_qty","vol_rate"): A[c2]=T[c2].values
del T,X,L,S
for h in (15,30): A[f"n{h}"]=(g.close.shift(-h)/A.buy-1)*100-A.cost
ok=A.lr.notna()&A.sr.notna()
print(f"두 비율이 다 있는 행 {int(ok.sum()):,} · 기간 {A.loc[ok,'date'].min()}~{A.loc[ok,'date'].max()} "
      f"· 그중 2023년 이후 {A.loc[ok,'date'].ge('20230101').mean():.0%}\n")
HOLDS=(5,10,15,20,30)
def block(t,cond,mk=None,reg=None,minn=30):
    print(f"── {t}"); hdr()
    for h in HOLDS: go(f"  {h}일", cond, hold=h, mk=mk, reg=reg, minn=minn)
    print()
print("■ 격자: 대차잔고 비율(lr) × 공매도 비중 비율(sr) · 20일 보유 · 코스피+코스닥"); hdr()
for l in (0.7,0.8,0.9):
    for s in (1.1,1.3,1.5,2.0):
        go(f"  대차<{l} · 공매도>{s}", (A.lr<l)&(A.sr>s), hold=20, minn=30)
print()
block("원안: 대차 <0.8 · 공매도 >1.3", (A.lr<0.8)&(A.sr>1.3))
block("원안 · 코스피", (A.lr<0.8)&(A.sr>1.3), mk="KOSPI")
block("원안 · 코스닥", (A.lr<0.8)&(A.sr>1.3), mk="KOSDAQ")
print("■ 각 축 단독 (20일)"); hdr()
for l in (0.7,0.8,0.9): go(f"  대차 <{l} 단독", A.lr<l, hold=20, minn=30)
for s in (1.1,1.3,1.5,2.0): go(f"  공매도 >{s} 단독", A.sr>s, hold=20, minn=30)
print()
print("■ 뒤집기·다른 조합 (20일)"); hdr()
go("  대차↑ >1.2 · 공매도↓ <0.8", (A.lr>1.2)&(A.sr<0.8), hold=20, minn=30)
go("  대차↓ <0.8 · 공매도↓ <0.8 (숏커버)", (A.lr<0.8)&(A.sr<0.8), hold=20, minn=30)
go("  대차↑ >1.2 · 공매도↑ >1.3", (A.lr>1.2)&(A.sr>1.3), hold=20, minn=30)
print()
block("원안 + 60일선 위", (A.lr<0.8)&(A.sr>1.3)&(A.dma60>0))
block("원안 + 20일 -10% 이하 낙폭", (A.lr<0.8)&(A.sr>1.3)&(A.ret20<=-10))
print("■ 국면별 (원안 · 20일)"); hdr()
for rg in ("UP","SIDE","DN"): go(f"  {rg}", (A.lr<0.8)&(A.sr>1.3), hold=20, reg=rg, minn=25)
Y=go("원안 20일", (A.lr<0.8)&(A.sr>1.3), hold=20, minn=1, quiet=True)
if len(Y):
    yr=Y.groupby("yr").agg(n=("r","size"),avg=("r","mean"),win=("r",lambda s:(s>0).mean()*100))
    print("\n연도별(원안·20일): "+" · ".join(f"{y}:{int(r.n)}건 {r.avg:+.1f}%({r.win:.0f}%)" for y,r in yr.iterrows()))
