# -*- coding: utf-8 -*-
"""국내 차트 강의(성승현) 실측 — 월봉 10이평 · 꼬리+거래량 · 위치별 거래량 해석.

강의 주장(2026-09-07 사용자 제공):
  ① 월봉 10이평(=10개월 ≒ 200거래일) 위면 상승추세. 이탈 판단은 장중이 아니라 '종가' 기준.
  ② 캔들은 색만 보지 말고 꼬리와 거래량을 함께 봐야 진짜 매수·매도 에너지가 보인다.
  ③ **거래량의 의미는 주가의 위치에 따라 달라진다** — 바닥권 거래량 수반은 긍정,
     급등 후 고점권 거래량 급증은 세력의 물량 처분일 가능성이 높다.
  ④ 추세(특정 가격대를 지키는가)가 본질이고, 단순할수록 강하다.
③ 이 우리가 안 재본 축이다. 우리는 거래량 급증(su1)을 쓰지만 '주가 위치' 와 곱해서 본 적이 없다.
위치 5분위 × 거래량 5분위 = 25칸 격자로 편다. 25칸을 보고 좋은 칸을 고르면 과적합이므로,
학습(2016~22)과 검증(2023~26)을 나란히 찍어 같은 자리가 살아남는지로 판정한다.
"""
import io, os, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
HS = [5, 20, 60]
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, base = ns["KP"], ns["KQ"], ns["base"]
for K in (KP, KQ):
    g = K.groupby("ticker", sort=False)
    for h in HS:
        if f"n{h}" not in K.columns: K[f"n{h}"] = (g.close.shift(-h)/K.buy-1)*100 - K.cost
    K["ma200"] = g.close.transform(lambda s: s.rolling(200, min_periods=200).mean())
    K["above200"] = K.close > K.ma200                       # ① 월봉 10이평 위(종가 기준)
    rng = (K.high - K.low).replace(0, np.nan)
    K["lower_tail"] = (K[["open","close"]].min(axis=1) - K.low) / rng   # ② 아래꼬리 비율
    K["upper_tail"] = (K.high - K[["open","close"]].max(axis=1)) / rng  # 윗꼬리 비율
    # ③ 위치: 52주 고저 사이 어디인가(0=저점, 100=고점).
    # ⚠ fromhi·fromlo 는 **퍼센트** 다((c/hi-1)*100). 소수로 쓰면 위치가 통째로 틀린다
    #   (2026-09-07 첫 구현의 버그 — 고점권 표본이 통째로 비었다). 고가·저가를 되돌려 직접 잰다.
    _hi = K.close / (1 + K.fromhi/100)
    _lo = K.close / (1 + K.fromlo/100)
    K["pos"] = ((K.close - _lo) / (_hi - _lo).replace(0, np.nan) * 100).clip(0, 100)
def uni(K, h): return K.dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean()
def ex_stats(K, m, h):
    col = f"n{h}"; z = K[m].dropna(subset=[col])
    if len(z) < 200: return None
    return (z[col] - z.date.map(uni(K, h))).mean(), len(z)
def grid(K, mkt, h=20):
    b = base(K, 3) & K.pos.notna() & K.su1.notna() & K[f"n{h}"].notna()
    tr = b & (K.date >= "20160101") & (K.date <= "20221231")
    va = b & (K.date >= "20230101")
    pq = pd.qcut(K.loc[b, "pos"], 5, labels=False, duplicates="drop")
    vq = pd.qcut(K.loc[b, "su1"], 5, labels=False, duplicates="drop")
    K["_pq"] = np.nan; K["_vq"] = np.nan
    K.loc[b, "_pq"] = pq.values; K.loc[b, "_vq"] = vq.values
    PL = ["바닥권", "하단", "중간", "상단", "고점권"]
    VL = ["거래량 최저", "적음", "보통", "많음", "급증"]
    print(f"\n[{mkt}] 위치 × 당일거래량 격자 — {h}일 보유 유니버스 대비 초과 (학습 / 검증)")
    print(f"  {'':<10}" + "".join(f"{v:>20}" for v in VL))
    for i in range(5):
        row = f"  {PL[i]:<10}"
        for j in range(5):
            mm = (K._pq == i) & (K._vq == j)
            a = ex_stats(K, mm & tr, h); c = ex_stats(K, mm & va, h)
            row += f"{a[0] if a else float('nan'):>+9.2f}/{c[0] if c else float('nan'):>+8.2f}"
        print(row)
for K, mkt in ((KP,"코스피"), (KQ,"코스닥")):
    print("="*118); print(f"[{mkt}]"); print("="*118)
    b = base(K, 3) & (K.date >= "20160101")
    print("  ① 월봉 10이평(200일선) — 종가 기준 위/아래 · 유니버스 대비 초과")
    for lab, m in (("200일선 위", b & (K.above200 == True)), ("200일선 아래", b & (K.above200 == False))):
        out = f"  {lab:<16}"
        for h in HS:
            r = ex_stats(K, m, h); out += f" n{h} {r[0]:>+6.2f}%({r[1]:>7,})" if r else f" n{h} —"
        print(out)
    print("  ② 꼬리 — 아래꼬리 긴 캔들 / 윗꼬리 긴 캔들 (거래량 급증 여부로 나눔)")
    for lab, m in (("아래꼬리≥50%", b & (K.lower_tail >= 0.5)),
                   ("아래꼬리≥50% + 거래량 2배↑", b & (K.lower_tail >= 0.5) & (K.su1 >= 2)),
                   ("윗꼬리≥50%", b & (K.upper_tail >= 0.5)),
                   ("윗꼬리≥50% + 거래량 2배↑", b & (K.upper_tail >= 0.5) & (K.su1 >= 2))):
        out = f"  {lab:<26}"
        for h in HS:
            r = ex_stats(K, m, h); out += f" n{h} {r[0]:>+6.2f}%({r[1]:>7,})" if r else f" n{h} —"
        print(out)
    print("  ③ 강의 핵심 — 바닥권/고점권 × 거래량 급증")
    for lab, m in (("바닥권(저점 20% 이내) + 거래량 2배↑", b & (K.pos <= 20) & (K.su1 >= 2)),
                   ("고점권(고점 20% 이내) + 거래량 2배↑", b & (K.pos >= 80) & (K.su1 >= 2)),
                   ("바닥권 + 거래량 3배↑", b & (K.pos <= 20) & (K.su1 >= 3)),
                   ("고점권 + 거래량 3배↑", b & (K.pos >= 80) & (K.su1 >= 3))):
        out = f"  {lab:<34}"
        for h in HS:
            r = ex_stats(K, m, h); out += f" n{h} {r[0]:>+6.2f}%({r[1]:>7,})" if r else f" n{h} —"
        print(out)
    grid(K, mkt, 20)
    print()
