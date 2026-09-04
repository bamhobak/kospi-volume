# -*- coding: utf-8 -*-
"""공매도가 식는 종목 × 프로그램 매매(차익·비차익) 증감 조합 실측.
공매도: sr = 비중 20일평균 / 250일평균  (식음 = 낮을수록)
프로그램 순매수 강도: pn20 = 20일 누적 비차익 순매수 / 20일 누적 거래량 ×100 (외인 fw20 와 같은 방식)
프로그램 활발도: pvr = 프로그램 매매비중 20일평균 / 250일평균 (규모 자체가 늘었나)
데이터는 둘 다 2019-04~ → 250일 평균이 서는 2020-04 부터 신호. 판단은 유니버스 대비 초과로.
"""
import sqlite3, warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from techlib import *
c=sqlite3.connect(f"file:{BASE}/data/toss.db?mode=ro",uri=True)
P=pd.read_sql("select date,ticker,arb_buy,arb_sell,arb_net,narb_buy,narb_sell,narb_net from program",c)
S=pd.read_sql("select date,ticker,vol_rate from short where vol_rate is not null",c); c.close()
X=P.merge(S,on=["date","ticker"],how="outer").sort_values(["ticker","date"])
V=A[["date","ticker","volume"]]
X=X.merge(V,on=["date","ticker"],how="left")
gX=X.groupby("ticker",sort=False)
r20=lambda s: gX[s].transform(lambda x: x.rolling(20,min_periods=15).sum())
X["v20s"]=r20("volume").replace(0,np.nan)
X["pn20"]=r20("narb_net")/X.v20s*100          # 비차익 순매수 강도(%)
X["pa20"]=r20("arb_net")/X.v20s*100           # 차익 순매수 강도(%)
X["pn5"]=gX.narb_net.transform(lambda x: x.rolling(5,min_periods=3).sum())/gX.volume.transform(lambda x: x.rolling(5,min_periods=3).sum()).replace(0,np.nan)*100
X["ptot"]=(X.arb_buy+X.arb_sell+X.narb_buy+X.narb_sell)
X["pv20"]=r20("ptot")/X.v20s*100              # 프로그램 매매 비중(%)
X["pv250"]=gX.pv20.transform(lambda x: x.rolling(250,min_periods=200).mean())
X["pvr"]=X.pv20/X.pv250.replace(0,np.nan)     # 프로그램 활발도 증감
X["sh20"]=gX.vol_rate.transform(lambda x: x.rolling(20,min_periods=15).mean())
X["sh250"]=gX.vol_rate.transform(lambda x: x.rolling(250,min_periods=200).mean())
X["sr"]=X.sh20/X.sh250.replace(0,np.nan)
n0=len(A); T=A.merge(X[["date","ticker","pn20","pa20","pn5","pv20","pvr","sr"]],on=["ticker","date"],how="left"); assert len(T)==n0
for c2 in ("pn20","pa20","pn5","pv20","pvr","sr"): A[c2]=T[c2].values
del T,X,P,S,V
for h in (15,30): A[f"n{h}"]=(g.close.shift(-h)/A.buy-1)*100-A.cost
ok=A.sr.notna()&A.pn20.notna()
print(f"두 값 다 있는 행 {int(ok.sum()):,} · 기간 {A.loc[ok,'date'].min()}~{A.loc[ok,'date'].max()} · 2023년 이후 {A.loc[ok,'date'].ge('20230101').mean():.0%}\n")
COOL = A.sr<0.7
print("■ 기준선 — 공매도 식음 단독 (20일)"); hdr()
for t in (0.5,0.6,0.7,0.8): go(f"  공매도 <{t}", A.sr<t, hold=20, minn=30)
print()
print("■ 격자 A: 공매도 식음(<0.7) × 비차익 순매수 강도 pn20 (20일)"); hdr()
for lo,hi,nm in ((-99,-0.5,"pn20 < -0.5 (팔고있다)"),(-0.5,0,"pn20 -0.5~0"),(0,0.5,"pn20 0~0.5"),
                 (0.5,1,"pn20 0.5~1"),(1,2,"pn20 1~2"),(2,99,"pn20 > 2 (강하게 산다)")):
    go(f"  {nm}", COOL&(A.pn20>=lo)&(A.pn20<hi), hold=20, minn=30)
print()
print("■ 격자 B: 공매도 식음 × 프로그램 활발도 pvr (20일)"); hdr()
for lo,hi,nm in ((0,0.7,"pvr <0.7 (프로그램 식음)"),(0.7,1.0,"pvr 0.7~1.0"),(1.0,1.3,"pvr 1.0~1.3"),
                 (1.3,2.0,"pvr 1.3~2.0"),(2.0,99,"pvr >2.0 (프로그램 급증)")):
    go(f"  {nm}", COOL&(A.pvr>=lo)&(A.pvr<hi), hold=20, minn=30)
print()
print("■ 격자 C: 공매도 식음 × 차익 순매수 pa20 (20일)"); hdr()
for lo,hi,nm in ((-99,-0.3,"pa20 < -0.3"),(-0.3,0.3,"pa20 -0.3~0.3"),(0.3,99,"pa20 > 0.3")):
    go(f"  {nm}", COOL&(A.pa20>=lo)&(A.pa20<hi), hold=20, minn=30)
print()
print("■ 유망 조합의 보유기간 (공매도<0.7 · pn20>1)"); hdr()
for h in (5,10,15,20,30): go(f"  {h}일", COOL&(A.pn20>1), hold=h, minn=30)
print()
print("■ 조이기 (20일)"); hdr()
go("  공매도<0.5 · pn20>1", (A.sr<0.5)&(A.pn20>1), hold=20, minn=30)
go("  공매도<0.7 · pn20>1 · pvr>1.2", COOL&(A.pn20>1)&(A.pvr>1.2), hold=20, minn=30)
go("  공매도<0.7 · pn20>1 · 60일선 위", COOL&(A.pn20>1)&(A.dma60>0), hold=20, minn=30)
go("  공매도<0.7 · pn20>1 · 외인20 ≥1", COOL&(A.pn20>1)&(A.fw20>=1), hold=20, minn=30)
go("  공매도<0.7 · pn5>2 (최근 5일 강매수)", COOL&(A.pn5>2), hold=20, minn=30)
print()
print("■ 뒤집기: 공매도 늘고 프로그램 판다 (20일)"); hdr()
go("  공매도>1.3 · pn20<-0.5", (A.sr>1.3)&(A.pn20<-0.5), hold=20, minn=30)
print()
print("■ 시장·국면별 (공매도<0.7 · pn20>1 · 20일)"); hdr()
for mk in ("KOSPI","KOSDAQ"): go(f"  {mk}", COOL&(A.pn20>1), hold=20, mk=mk, minn=25)
for rg in ("UP","SIDE","DN"): go(f"  {rg}", COOL&(A.pn20>1), hold=20, reg=rg, minn=25)
Y=go("", COOL&(A.pn20>1), hold=20, minn=1, quiet=True)
if len(Y):
    yr=Y.groupby("yr").agg(n=("r","size"),avg=("r","mean"),med=("r","median"),win=("r",lambda s:(s>0).mean()*100),al=("alpha","mean"))
    print("\n연도별(공매도<0.7·pn20>1·20일)")
    for y,r in yr.iterrows(): print(f"   {y}  {int(r.n):>4}건  평균 {r.avg:>+6.2f}%  중앙 {r.med:>+5.1f}  승률 {r.win:>3.0f}%  초과 {r.al:>+5.2f}")
    print(f"   최다 연도 비중 {Y.yr.value_counts(normalize=True).max():.0%}")
