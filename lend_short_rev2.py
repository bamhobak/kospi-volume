# -*- coding: utf-8 -*-
"""반대해석 재검증 — 날짜 매칭 벤치마크로 바로잡고, 가설 A 최적 셀의 연도별·중앙값을 본다."""
import sqlite3, warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from techlib import *
c=sqlite3.connect(f"file:{BASE}/data/toss.db?mode=ro",uri=True)
L=pd.read_sql("select date,ticker,bal_qty from lending where bal_qty is not null",c)
S=pd.read_sql("select date,ticker,vol_rate from short where vol_rate is not null",c); c.close()
X=L.merge(S,on=["date","ticker"],how="outer").sort_values(["ticker","date"]); gX=X.groupby("ticker",sort=False)
X["lr"]=gX.bal_qty.transform(lambda s: s.rolling(20,min_periods=15).mean())/gX.bal_qty.transform(lambda s: s.rolling(250,min_periods=200).mean()).replace(0,np.nan)
X["sr"]=gX.vol_rate.transform(lambda s: s.rolling(20,min_periods=15).mean())/gX.vol_rate.transform(lambda s: s.rolling(250,min_periods=200).mean()).replace(0,np.nan)
n0=len(A); T=A.merge(X[["date","ticker","lr","sr"]],on=["ticker","date"],how="left"); assert len(T)==n0
A["lr"]=T.lr.values; A["sr"]=T.sr.values; del T,X,L,S
for h in (15,30): A[f"n{h}"]=(g.close.shift(-h)/A.buy-1)*100-A.cost
print("■ 가설 C 재계산 — 같은 날 유니버스와 비교(dedup 적용, go() 기준)")
print("   원안(대차<0.8·공매도>1.3) 롱 초과가 음수여야 숏이 돈이 된다\n"); hdr()
for h in (5,10,15,20,30): go(f"  롱 {h}일", (A.lr<0.8)&(A.sr>1.3), hold=h, minn=30)
print("\n   → 숏 성과 = 롱 초과의 부호 반전 (대차수수료·업틱룰 무시한 상한선)")
print("\n■ 가설 A 최적 셀(대차>1.5·공매도>1.3) 연도별 · 20일")
Y=go("", (A.lr>1.5)&(A.sr>1.3), hold=20, minn=1, quiet=True)
if len(Y):
    yr=Y.groupby("yr").agg(n=("r","size"),avg=("r","mean"),med=("r","median"),win=("r",lambda s:(s>0).mean()*100),al=("alpha","mean"))
    for y,r in yr.iterrows(): print(f"   {y}  {int(r.n):>4}건  평균 {r.avg:>+6.2f}%  중앙 {r.med:>+5.1f}  승률 {r.win:>3.0f}%  초과 {r.al:>+5.2f}")
    print(f"   최다 연도 비중 {Y.yr.value_counts(normalize=True).max():.0%} · 전체 중앙값 {Y.r.median():+.2f}")
print("\n■ 대차잔고 축을 우리 규칙 재료로 — 초과수익 기준 문턱 스윕 (20일)"); hdr()
for lo,hi,nm in ((0,0.6,"대차 <0.6"),(0.6,0.8,"대차 0.6~0.8"),(0.8,1.0,"대차 0.8~1.0"),
                 (1.0,1.3,"대차 1.0~1.3"),(1.3,2.0,"대차 1.3~2.0"),(2.0,99,"대차 >2.0")):
    go(f"  {nm}", (A.lr>=lo)&(A.lr<hi), hold=20, minn=30)
print("\n■ 공매도 축 문턱 스윕 (20일)"); hdr()
for lo,hi,nm in ((0,0.7,"공매도 <0.7"),(0.7,1.0,"공매도 0.7~1.0"),(1.0,1.5,"공매도 1.0~1.5"),
                 (1.5,2.5,"공매도 1.5~2.5"),(2.5,99,"공매도 >2.5")):
    go(f"  {nm}", (A.sr>=lo)&(A.sr<hi), hold=20, minn=30)
