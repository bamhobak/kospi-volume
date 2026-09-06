# -*- coding: utf-8 -*-
"""오늘 낸 수익률·수익금·승률의 재료가 맞는지 — 계산이 아니라 데이터부터 뜯는다.

의심 항목:
  ① 수정주가인가 — 액면분할이 '폭락' 으로 잡히면 가짜 신호가 된다
  ② OHLC 가 진짜인가 — 시가·고가·저가가 종가로 채워진 행(가짜)이 있으면 진입가·손절이 틀어진다
  ③ 중복 행 · 거래량 0 행
  ④ 폐지 종목의 청산가 처리
  ⑤ 과거 패널(panel_kp)과 운영 패널(kp_ow)이 겹치는 2018~26 에서 같은 답을 내는가
사용: python audit_data.py
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path
BASE = Path(__file__).parent

KP = pd.read_pickle(BASE/"data"/"panel_kp.pkl")
print(f"panel_kp: {len(KP):,}행 · {KP.date.min()}~{KP.date.max()} · 열 {len(KP.columns)}")

print("\n① 수정주가 여부 — 알려진 액면분할 전후 종가")
SPLITS = [("005930","삼성전자","20180503","20180504","50:1"), ("035420","NAVER","20181011","20181012","5:1"),
          ("090430","아모레퍼시픽","20150507","20150508","10:1"), ("035720","카카오","20210414","20210415","5:1")]
for t, nm, d0, d1, r in SPLITS:
    a = KP[(KP.ticker==t)&(KP.date==d0)]; b = KP[(KP.ticker==t)&(KP.date==d1)]
    if len(a) and len(b):
        ca, cb = a.close.iloc[0], b.close.iloc[0]
        print(f"  {nm:<8}{r:>5} {d0} {ca:>12,.0f} → {d1} {cb:>12,.0f}  비율 {ca/cb:>5.1f}  "
              f"{'⚠ 미수정(원주가)' if ca/cb>2 else '수정주가'}  bad플래그={bool(b.bad.iloc[0])}")
    else: print(f"  {nm}: 패널에 없음 ({len(a)},{len(b)})")

print("\n② 하루 ±32% 넘는 점프(분할·병합 의심) 행 수와 그것이 신호에 끼는지")
KP = KP.sort_values(["ticker","date"]); g = KP.groupby("ticker", sort=False)
jj = KP.close/g.close.shift(1)
big = KP[(jj>1.32)|(jj<0.68)]
KP["_y"] = KP.date.str[:4]
print("  연도별 점프 행:", " · ".join(f"{y}:{n}" for y,n in big.groupby(big.date.str[:4]).size().items()))
print(f"  bad 플래그 행 비율: {KP.bad.mean()*100:.2f}%  (규칙 base() 에서 bad 를 거르는가는 grep 결과 참조)")

print("\n③ OHLC 진위 — 시=고=저=종 인 행 비율(가짜 OHLC 의심) · 거래량 0 · 중복")
flat = (KP.open==KP.high)&(KP.high==KP.low)&(KP.low==KP.close)
r = flat.groupby(KP._y).mean()*100
print("  시고저종 동일:", " · ".join(f"{y}:{v:.1f}%" for y,v in r.items()))
z = (KP.volume<=0).groupby(KP._y).mean()*100
print("  거래량 0    :", " · ".join(f"{y}:{v:.1f}%" for y,v in z.items()))
print(f"  (ticker,date) 중복: {KP.duplicated(['ticker','date']).sum():,}행")
lowmiss = KP.low.isna().groupby(KP._y).mean()*100
print("  저가 결측    :", " · ".join(f"{y}:{v:.1f}%" for y,v in lowmiss.items() if v>0) or "  없음")

print("\n④ 폐지 종목 — 마지막 거래일 근처 청산 처리")
last = g.date.transform("max"); KP["_last"] = last
D = KP[KP.grp!="생존"] if "grp" in KP.columns else KP.iloc[0:0]
print(f"  폐지 그룹 행 {len(D):,} · 종목 {D.ticker.nunique():,}")
tail = D[D.date==D._last]
print(f"  마지막 날 n20 이 NaN 인 비율: {tail.n20.isna().mean()*100:.1f}%  (NaN 이면 측정에서 빠진다 → 생존편향)")
print(f"  마지막 날 종가 중앙값 {tail.close.median():,.0f}원 · 1,000원 미만 {(tail.close<1000).mean()*100:.0f}%")

print("\n⑤ 거래비용 가정")
print(f"  cost 분포: 최소 {KP.cost.min():.2f}% · 중앙 {KP.cost.median():.2f}% · 최대 {KP.cost.max():.2f}%  (세금 0.18 + 슬리피지 0.2~1.0)")
print("  ⚠ 거래세 실제: ~2018 0.30% · 2019~20 0.25% · 2021~22 0.23% · 2023 0.20% · 2024 0.18% · 2025~ 0.15%")
