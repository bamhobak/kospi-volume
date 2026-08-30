# -*- coding: utf-8 -*-
"""방어조건 조합 + 실제 D1 수익 영향"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
import FinanceDataReader as fdr
D=pd.read_pickle("data/kd_risk.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
g=D.groupby("ticker",sort=False)
D["ret20"]=g.close.transform(lambda x:x/x.shift(20)-1)*100
a20=g["volume"].transform(lambda x:x.shift(1).rolling(20).mean())
D["vs1"]=D.volume/a20
dates=sorted(D.date.unique())
ki=fdr.DataReader("KS11","2016-06-01");ki=ki[ki.Close>0];ki.index=ki.index.strftime("%Y%m%d")
kc=ki["Close"].reindex(dates).ffill()
D["k60"]=D.date.map(kc>kc.rolling(60).mean()).fillna(False).values
CORE=((D.ret20<=-20)&(D.vs1>=2)&(D.fw60>=1)&(~D.k60)&(D.amt20>=2)).fillna(False)
PRE=CORE&(D.grp=="폐지")&D.m2d.between(0,24); ALV=CORE&(D.grp=="생존")&(D.date>="20190101")
print("## 조합 — 폐지비중 낮추면서 신호 손실 최소\n")
print("| 조건 | 폐지 통과 | 정상 통과 | 손실률 | **폐지비중** |\n|---|---|---|---|---|")
a0=ALV.sum()
COMB=[("현행",pd.Series(True,index=D.index)),
      ("주가≥1,000원",D.close>=1000),
      ("주가≥1,000 + 1년수익>-70%",(D.close>=1000)&(D.ret250>-70)),
      ("주가≥1,000 + 1년수익>-60%",(D.close>=1000)&(D.ret250>-60)),
      ("주가≥2,000 + 1년수익>-70%",(D.close>=2000)&(D.ret250>-70)),
      ("주가≥1,000 + 외국인지분≥1%",(D.close>=1000)&(D.foreign_ratio>=1)),
      ("주가≥1,000 + 1년수익>-70% + 외국인지분≥1%",(D.close>=1000)&(D.ret250>-70)&(D.foreign_ratio>=1))]
for nm,m in COMB:
    m=m.fillna(False) if hasattr(m,"fillna") else m
    p=int((PRE&m).sum()); a=int((ALV&m).sum())
    print(f"| {nm} | {p}건 | {a:,}건 | {(1-a/a0)*100:.0f}% | **{p/max(p+a,1)*100:.2f}%** |")

# ── 실제 D1 백테스트에 얹었을 때 수익 영향 ─────────────────────
print("\n## 실제 D1 거래(842건)에 얹었을 때\n")
T=pd.read_csv("data/kd_trades_del.csv",dtype={"date":str,"ticker":str})
T.columns=[c.lstrip("\ufeff") for c in T.columns]
key=D.set_index(["date","ticker"])[["close","ret250","foreign_ratio"]]
T=T.join(key,on=["date","ticker"])
print(f"지표 결합: 주가 {T.close.notna().mean()*100:.0f}% · 1년수익 {T.ret250.notna().mean()*100:.0f}% · 외국인지분 {T.foreign_ratio.notna().mean()*100:.0f}%\n")
print("| 조건 | 건수 | 보존율 | 전체 평균 | **검증 평균** | 검증 승률 | 최악 |\n|---|---|---|---|---|---|---|")
n0=len(T)
for nm,m in [("현행",pd.Series(True,index=T.index)),
             ("주가≥1,000원",T.close>=1000),
             ("주가≥1,000 + 1년수익>-70%",(T.close>=1000)&(T.ret250>-70)),
             ("주가≥2,000 + 1년수익>-70%",(T.close>=2000)&(T.ret250>-70)),
             ("주가≥1,000 + 1년수익>-70% + 외국인지분≥1%",(T.close>=1000)&(T.ret250>-70)&(T.foreign_ratio>=1))]:
    m=(m.fillna(True) if hasattr(m,"fillna") else m)      # 데이터 없으면 통과
    s=T[m]; v=s[s.y>=2023].r
    print(f"| {nm} | {len(s)} | {len(s)/n0*100:.0f}% | {s.r.mean():+.2f}% | **{v.mean():+.2f}%** | {(v>0).mean()*100:.0f}% | {s.r.min():.1f}% |")
