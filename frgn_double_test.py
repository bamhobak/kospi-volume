# -*- coding: utf-8 -*-
"""외인 지분율: 최근 한 달 평균이 1년 평균의 2배 초과가 되는 순간 매수 → 5/10/15/20/30일."""
import sqlite3, warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from techlib import *
F=[]
for db in ("kospi.db","kosdaq.db"):
    c=sqlite3.connect(f"file:{BASE}/data/{db}?mode=ro",uri=True)
    F.append(pd.read_sql("select date,ticker,foreign_ratio fr from daily where date>='20170101' and foreign_ratio is not null",c)); c.close()
F=pd.concat(F).drop_duplicates(["ticker","date"]).sort_values(["ticker","date"])
gF=F.groupby("ticker",sort=False)
F["fr250"]=gF.fr.transform(lambda s: s.rolling(250,min_periods=200).mean())
F["fr20"]=gF.fr.transform(lambda s: s.rolling(20).mean())
n0=len(A); T=A.merge(F[["ticker","date","fr","fr250","fr20"]],on=["ticker","date"],how="left"); assert len(T)==n0
for c in ("fr","fr250","fr20"): A[c]=T[c].values
del T,F
for h in (15,30): A[f"n{h}"]=(g.close.shift(-h)/A.buy-1)*100-A.cost
A["rat"]=A.fr20/A.fr250
A["rat_p"]=g.rat.shift(1)
cross=(A.rat>2)&(A.rat_p<=2)&(A.fr250>=2)      # '넘는 순간'
stay =(A.rat>2)&(A.fr250>=2)                    # 넘어 있는 상태 아무 날
print(f"2배 초과 상태 {int(stay.sum()):,}행 · 넘는 순간 {int(cross.sum()):,}행 · 종목 {A[cross.fillna(False)].ticker.nunique():,}개\n")
HOLDS=(5,10,15,20,30)
def block(t,c,mk=None,reg=None,minn=25):
    print(f"── {t} (유니버스 20일 {base(20,mk=mk,reg=reg):+.2f}%)"); hdr()
    for h in HOLDS: go(f"  {h}일", c, hold=h, mk=mk, reg=reg, minn=minn)
    print()
block("원안: 2배 초과로 올라서는 순간", cross)
block("원안 · 코스피", cross, mk="KOSPI")
block("원안 · 코스닥", cross, mk="KOSDAQ")
block("변형: 2배 초과 상태(아무 날)", stay)
block("변형: 1.5배 초과로 올라서는 순간", (A.rat>1.5)&(g.rat.shift(1)<=1.5)&(A.fr250>=2))
block("변형: 3배 초과로 올라서는 순간", (A.rat>3)&(g.rat.shift(1)<=3)&(A.fr250>=2))
block("변형: 2배 초과 + 1년 평균 지분율 ≥5%", cross&(A.fr250>=5))
block("변형: 2배 초과 + 당일 외인 순매수", cross&(A.frgn>0))
block("변형: 2배 초과 + 60일선 위", cross&(A.dma60>0))
print("── 국면별 (원안 · 20일)"); hdr()
for rg in ("UP","SIDE","DN"): go(f"  {rg}", cross, hold=20, reg=rg, minn=25)
Y=go("원안 20일", cross, hold=20, minn=1, quiet=True)
if len(Y):
    yr=Y.groupby("yr").agg(n=("r","size"),avg=("r","mean"),win=("r",lambda s:(s>0).mean()*100))
    print("\n연도별(원안·20일): "+" · ".join(f"{y}:{int(r.n)}건 {r.avg:+.1f}%({r.win:.0f}%)" for y,r in yr.iterrows()))
