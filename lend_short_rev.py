# -*- coding: utf-8 -*-
"""반대해석 실측 — 대차잔고를 '숏 압력'이 아니라 '기관 관심도'로 읽는다.
가설 A: 대차잔고 증가 = 그 종목에 돈이 몰린다(빌려서라도 다룬다) → 매수
가설 B: 대차잔고 감소 = 관심 소멸 → 회피(우리 규칙의 제외 필터)
가설 C: 원안(대차↓·공매도↑)을 공매도(숏) 관점으로 — 부호를 뒤집으면 돈이 되나
판단은 절대수익이 아니라 '유니버스 대비 초과' 로 한다(2022년 이후 유니버스가 음수라서).
"""
import sqlite3, warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from techlib import *
c=sqlite3.connect(f"file:{BASE}/data/toss.db?mode=ro",uri=True)
L=pd.read_sql("select date,ticker,bal_qty,bal_amt from lending where bal_qty is not null",c)
S=pd.read_sql("select date,ticker,vol_rate from short where vol_rate is not null",c); c.close()
X=L.merge(S,on=["date","ticker"],how="outer").sort_values(["ticker","date"])
gX=X.groupby("ticker",sort=False)
X["lend20"]=gX.bal_qty.transform(lambda s: s.rolling(20,min_periods=15).mean())
X["lend250"]=gX.bal_qty.transform(lambda s: s.rolling(250,min_periods=200).mean())
X["sh20"]=gX.vol_rate.transform(lambda s: s.rolling(20,min_periods=15).mean())
X["sh250"]=gX.vol_rate.transform(lambda s: s.rolling(250,min_periods=200).mean())
X["lr"]=X.lend20/X.lend250.replace(0,np.nan)
X["sr"]=X.sh20/X.sh250.replace(0,np.nan)
X["lr5"]=gX.bal_qty.transform(lambda s: s.rolling(5,min_periods=3).mean())/X.lend250.replace(0,np.nan)
n0=len(A); T=A.merge(X[["date","ticker","lr","sr","lr5"]],on=["ticker","date"],how="left"); assert len(T)==n0
for c2 in ("lr","sr","lr5"): A[c2]=T[c2].values
del T,X,L,S
for h in (15,30): A[f"n{h}"]=(g.close.shift(-h)/A.buy-1)*100-A.cost
HOLDS=(5,10,15,20,30)
print("■ 가설 A — 대차잔고 증가(관심도)를 매수로 · 20일 · 초과수익으로 판단"); hdr()
for l in (1.1,1.2,1.3,1.5,2.0): go(f"  대차 >{l} 단독", A.lr>l, hold=20, minn=30)
print()
print("■ 가설 A 격자: 대차 증가 × 공매도 (20일)"); hdr()
for l in (1.2,1.5,2.0):
    for s in (0.8,1.0,1.3,1.5):
        go(f"  대차>{l} · 공매도>{s}" if s>=1 else f"  대차>{l} · 공매도<{s}",
           (A.lr>l)&((A.sr>s) if s>=1 else (A.sr<s)), hold=20, minn=30)
print()
print("■ 가설 A 최적 후보의 보유기간 (대차>1.5 · 공매도>1.3)"); hdr()
for h in HOLDS: go(f"  {h}일", (A.lr>1.5)&(A.sr>1.3), hold=h, minn=30)
print()
print("■ 시장·국면별 (대차>1.5 · 공매도>1.3 · 20일)"); hdr()
for mk in ("KOSPI","KOSDAQ"): go(f"  {mk}", (A.lr>1.5)&(A.sr>1.3), hold=20, mk=mk, minn=25)
for rg in ("UP","SIDE","DN"): go(f"  {rg}", (A.lr>1.5)&(A.sr>1.3), hold=20, reg=rg, minn=25)
print()
print("■ 가설 B — 대차잔고 감소 종목을 '제외' 했을 때 남는 쪽 (20일)"); hdr()
go("  대차 ≥0.8 (감소 종목 제외)", A.lr>=0.8, hold=20, minn=30)
go("  대차 ≥1.0", A.lr>=1.0, hold=20, minn=30)
go("  대차 값 있는 전체(기준선)", A.lr.notna(), hold=20, minn=30)
print()
print("■ 가설 C — 원안(대차<0.8·공매도>1.3)을 공매도로 잡았을 때 (부호 반전 · 대차비용 무시)")
u=BASEU&(A.lr<0.8)&(A.sr>1.3)
for h in HOLDS:
    Y=A[u.fillna(False)].dropna(subset=[f"n{h}"])
    b=A[BASEU][f"n{h}"].mean()
    print(f"    {h}일  {len(Y):>5}건  롱 {Y[f'n{h}'].mean():>+6.2f}%  숏(부호반전) {-Y[f'n{h}'].mean():>+6.2f}%  "
          f"유니버스 {b:>+5.2f}  숏 초과 {-(Y[f'n{h}'].mean()-b):>+5.2f}  롱 승률 {(Y[f'n{h}']>0).mean():>4.0%}")
print("\n■ 참고: 대차 5일평균 기준(더 민감) · 20일"); hdr()
go("  대차5 <0.7 · 공매도>1.3", (A.lr5<0.7)&(A.sr>1.3), hold=20, minn=30)
go("  대차5 >1.5 · 공매도>1.3", (A.lr5>1.5)&(A.sr>1.3), hold=20, minn=30)
