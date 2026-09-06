# -*- coding: utf-8 -*-
"""2010~2012 코스피는 어떤 시장이었나 — 우리 계좌가 유일하게 못 넘은 3년.

계좌가 0.99배(연 -0.3%)로 제자리였다. 그런데 그게 '시장이 나빠서' 인지 '우리 규칙이 안 맞아서'
인지는 다르다. 지수·국면·유니버스 드리프트·업종 분산을 다른 구간과 나란히 놓고 본다.
사용: python market_1012.py
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

IX = fdr.DataReader("KS11", "2004-06-01"); IX = IX[IX.Close > 0].copy()
IX["d"] = IX.index.strftime("%Y%m%d")
IX["ma60"] = IX.Close.rolling(60).mean()
IX["gap"] = (IX.Close/IX.ma60 - 1)*100          # 국면 판정: ±5%
IX["rv"] = IX.Close.pct_change().rolling(20).std()*np.sqrt(252)*100
KQ_IX = fdr.DataReader("KQ11", "2004-06-01"); KQ_IX = KQ_IX[KQ_IX.Close > 0]

PER = [("2005~2007","2005","2007"), ("2008~2009","2008","2009"), ("2010~2012","2010","2012"),
       ("2013~2017","2013","2017"), ("2018~2022","2018","2022"), ("2023~2026","2023","2026")]
print("코스피 지수로 본 구간 성격")
print(f"  {'구간':<12}{'지수수익':>9}{'연복리':>8}{'최대낙폭':>9}{'변동성':>8}"
      f"{'상승장':>8}{'횡보장':>8}{'하락장':>8}{'코스닥':>9}")
print("  " + "-"*80)
for nm, y0, y1 in PER:
    z = IX[(IX.d >= y0+"0101") & (IX.d <= y1+"1231")]
    q = KQ_IX[(KQ_IX.index.strftime("%Y%m%d") >= y0+"0101") & (KQ_IX.index.strftime("%Y%m%d") <= y1+"1231")]
    r = (z.Close.iloc[-1]/z.Close.iloc[0]-1)*100
    yrs = len(z)/246; cagr = ((1+r/100)**(1/yrs)-1)*100
    mdd = ((z.Close/z.Close.cummax()-1)*100).min()
    up = (z.gap > 5).mean()*100; dn = (z.gap < -5).mean()*100
    kq = (q.Close.iloc[-1]/q.Close.iloc[0]-1)*100
    print(f"  {nm:<12}{r:>+8.0f}%{cagr:>+7.1f}%{mdd:>8.0f}%{z.rv.mean():>7.0f}%"
          f"{up:>7.0f}%{100-up-dn:>7.0f}%{dn:>7.0f}%{kq:>+8.0f}%")

print("\n2010~2012 연도별 코스피")
for y in ("2009","2010","2011","2012","2013"):
    z = IX[(IX.d >= y+"0101") & (IX.d <= y+"1231")]
    if not len(z): continue
    mdd = ((z.Close/z.Close.cummax()-1)*100).min()
    print(f"  {y}: 시작 {z.Close.iloc[0]:>7,.0f} → 끝 {z.Close.iloc[-1]:>7,.0f}"
          f" ({(z.Close.iloc[-1]/z.Close.iloc[0]-1)*100:>+6.1f}%) · 고점 {z.Close.max():>7,.0f}"
          f" · 저점 {z.Close.min():>7,.0f} · 최대낙폭 {mdd:>6.1f}% · 변동성 {z.rv.mean():>4.0f}%")

# 유니버스 드리프트 — 우리 규칙이 사는 곳(개별 종목)의 평균 20일 수익
import os
os.environ.setdefault("PANEL_KP", "panel_kp.pkl")
print("\n같은 기간 개별 종목 유니버스 (코스피 패널 · 20일 보유 평균)")
KP = pd.read_pickle("data/panel_kp.pkl")
g = KP.groupby("ticker", sort=False)
KP["f20"] = (g.close.shift(-20)/g.close.shift(-1)-1)*100
KP = KP[(KP.close >= 1000)]
for nm, y0, y1 in PER:
    z = KP[(KP.date >= y0+"0101") & (KP.date <= y1+"1231")].dropna(subset=["f20"])
    if not len(z): continue
    print(f"  {nm:<12} 평균 {z.f20.mean():>+6.2f}% · 중앙 {z.f20.median():>+6.2f}%"
          f" · 승률 {(z.f20>0).mean()*100:>4.0f}% · 표본 {len(z):,}")
