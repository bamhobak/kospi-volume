# -*- coding: utf-8 -*-
"""외인 지분율 1년 평균 대비 최근 한 달 절반 미만 + 최근 3일 외인 순매수 → 5/10/15/20/30일 보유."""
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
A["f1"]=g.frgn.shift(1); A["f2"]=g.frgn.shift(2)
buy3=(A.frgn>0)&(A.f1>0)&(A.f2>0); sum3=(A.frgn+A.f1+A.f2)>0
half=(A.fr20<0.5*A.fr250)&(A.fr250>=2)
print(f"외인비율 결측 제외 행 {A.fr250.notna().sum():,} · '절반 미만' 해당 행 {int(half.sum()):,} · 그중 3일 연속 순매수 {int((half&buy3).sum()):,}\n")
HOLDS=(5,10,15,20,30)
def block(title, cond, mk=None, reg=None):
    print(f"── {title} (유니버스 20일 {base(20,mk=mk,reg=reg):+.2f}%)"); hdr()
    for h in HOLDS: go(f"  {h}일", cond, hold=h, mk=mk, reg=reg, minn=25)
    print()
block("원안: 절반 미만 · 3일 연속 순매수 · 코스피+코스닥", half&buy3)
block("원안 · 코스피", half&buy3, mk="KOSPI")
block("원안 · 코스닥", half&buy3, mk="KOSDAQ")
block("변형: 3일 합계 순매수(연속 아님)", half&sum3)
block("변형: 절반→70% 미만", (A.fr20<0.7*A.fr250)&(A.fr250>=2)&buy3)
block("변형: 절반 미만 · 5일 연속 순매수", half&buy3&(g.frgn.shift(3)>0)&(g.frgn.shift(4)>0))
block("변형: 1년 평균 지분율 ≥5% 종목만", half&buy3&(A.fr250>=5))
block("변형: +외인 3일 순매수가 거래량의 1% 이상", half&buy3&(A.fw5>=1))
print("── 국면별 (원안 · 코스피+코스닥 · 20일)"); hdr()
for rg in ("UP","SIDE","DN"): go(f"  {rg}", half&buy3, hold=20, reg=rg, minn=25)
print("\n── 뒤집기: 최근 한 달 지분율이 1년 평균의 1.5배 이상 · 3일 연속 순매도"); hdr()
for h in (5,20): go(f"  {h}일", (A.fr20>1.5*A.fr250)&(A.fr250>=2)&(A.frgn<0)&(A.f1<0)&(A.f2<0), hold=h, minn=25)
Y=go("원안 20일", half&buy3, hold=20, minn=1, quiet=True)
if len(Y):
    yr=Y.groupby("yr").agg(n=("r","size"),avg=("r","mean"),win=("r",lambda s:(s>0).mean()*100))
    print("\n연도별(원안·20일): "+" · ".join(f"{y}:{int(r.n)}건 {r.avg:+.1f}%({r.win:.0f}%)" for y,r in yr.iterrows()))
