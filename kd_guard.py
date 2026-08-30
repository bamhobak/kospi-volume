# -*- coding: utf-8 -*-
"""코스닥 폐지위험 3 — 방어조건 후보의 효과와 비용
   효과 = 폐지 예정 종목이 D1 조건을 통과하는 빈도를 얼마나 줄이나
   비용 = 정상 D1 신호를 얼마나 잃나
"""
import io,sys,sqlite3,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
import FinanceDataReader as fdr
D=pd.read_pickle("data/kd_risk.pkl")
# D1 의 시세계열 조건만 재현(공매도·증자·업종 제외 — 폐지종목엔 그 데이터가 없다)
g=D.sort_values(["ticker","date"]).groupby("ticker",sort=False)
D=D.sort_values(["ticker","date"]).reset_index(drop=True); g=D.groupby("ticker",sort=False)
D["ret20"]=g.close.transform(lambda x:x/x.shift(20)-1)*100
a20=g["volume"].transform(lambda x:x.shift(1).rolling(20).mean())
D["vs1"]=D.volume/a20
dates=sorted(D.date.unique())
ki=fdr.DataReader("KS11","2016-06-01"); ki=ki[ki.Close>0]; ki.index=ki.index.strftime("%Y%m%d")
kc=ki["Close"].reindex(dates).ffill()
D["k60"]=D.date.map(kc>kc.rolling(60).mean()).fillna(False).values
CORE=((D.ret20<=-20)&(D.vs1>=2)&(D.fw60>=1)&(~D.k60)).fillna(False)
print("## D1 핵심조건(시세·외국인·시장국면)만 적용했을 때\n")
PRE=CORE&(D.grp=="폐지")&D.m2d.between(0,24)
ALV=CORE&(D.grp=="생존")&(D.date>="20190101")
print(f"- 폐지 24개월 전 통과: **{int(PRE.sum()):,}건** ({D[PRE].ticker.nunique()}종목)")
print(f"- 생존 종목 통과: {int(ALV.sum()):,}건 ({D[ALV].ticker.nunique()}종목)")
print(f"- 폐지 비중: **{PRE.sum()/(PRE.sum()+ALV.sum())*100:.2f}%**\n")
print("## 방어조건별 — 폐지 노출 감소 vs 정상 신호 손실\n")
print("| 추가 조건 | 폐지 통과 | 감소율 | 정상 통과 | 손실률 | **폐지비중** |\n|---|---|---|---|---|---|")
b0,a0=PRE.sum(),ALV.sum()
CAND=[("없음 (현행 거래대금 2억)",D.amt20>=2)]
for q in (5,10,20,30,50): CAND.append((f"거래대금 ≥ {q}억",D.amt20>=q))
for q in (1000,2000,3000,5000): CAND.append((f"주가 ≥ {q:,}원 (2억)",(D.close>=q)&(D.amt20>=2)))
for q in (1,3,5): CAND.append((f"외국인지분 ≥ {q}% (2억)",(D.foreign_ratio>=q)&(D.amt20>=2)))
for q in (-70,-50): CAND.append((f"1년수익 > {q}% (2억)",(D.ret250>q)&(D.amt20>=2)))
CAND.append(("거래대금 ≥ 10억 + 주가 ≥ 1,000원",(D.amt20>=10)&(D.close>=1000)))
CAND.append(("거래대금 ≥ 10억 + 외국인지분 ≥ 1%",(D.amt20>=10)&(D.foreign_ratio>=1)))
CAND.append(("거래대금 ≥ 20억 + 주가 ≥ 1,000원",(D.amt20>=20)&(D.close>=1000)))
for nm,m in CAND:
    m=m.fillna(False)
    p=int((PRE&m).sum()); a=int((ALV&m).sum())
    print(f"| {nm} | {p}건 | {(1-p/max(b0,1))*100:.0f}% | {a:,}건 | {(1-a/max(a0,1))*100:.0f}% | **{p/max(p+a,1)*100:.2f}%** |")
