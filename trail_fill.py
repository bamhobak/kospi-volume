# -*- coding: utf-8 -*-
"""트레일 -8% 의 **체결 가정**이 얼마나 낙관적인가 (2026-09-12).

portfolio.py 는 트레일이 걸린 날 `고점*(1-0.08)` **그 가격에** 판다고 본다. 현실에서는
그 가격을 지나쳐 내려간 뒤에야 알게 된다. 세 가지를 잰다.

  ① 발동일 종가가 가정 가격보다 얼마나 아래였나 (같은 날 종가에 판다면)
  ② 다음날 시가에 판다면 (종가 판정 → 익일 시가 매도가 현실에 가깝다)
  ③ 두 보수판으로 다시 재면 최악과 평균이 어떻게 되나

    python trail_fill.py
"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd

exec(open("portfolio.py", encoding="utf-8").read(), globals())

print("\n" + "=" * 100)
print("트레일 -8% — 가정 가격 · 발동일 종가 · 익일 시가 세 가지로 청산해 본다")
print("=" * 100)

for rid in ["P1", "P4", "P6"]:
    K, hold, stop, pct, mx, cond = RULES[rid]
    t = TRAIL[rid]
    g = K.groupby("ticker", sort=False)
    m = cond.fillna(False).values
    C = np.column_stack([g.close.shift(-i).values for i in range(1, hold + 1)])
    O = np.column_stack([g.open.shift(-i).values for i in range(1, hold + 2)])   # 익일까지 하나 더
    run = np.maximum.accumulate(np.column_stack([K.buy.values, C]), axis=1)[:, 1:]
    hit = C <= run * (1 - t)
    ok = hit.any(axis=1)
    first = np.where(ok, hit.argmax(axis=1), hold - 1)
    ar = np.arange(len(C))

    px_model = np.where(ok, run[ar, first] * (1 - t), C[:, -1])   # 지금 쓰는 가정
    px_close = np.where(ok, C[ar, first], C[:, -1])               # 발동일 종가
    px_open1 = np.where(ok, O[ar, first + 1], C[:, -1])           # 다음날 시가

    X = K[m].copy()
    buy = X.buy.values; cost = X.cost.values
    keep = np.isfinite(buy) & (buy > 0) & np.isfinite(cost)
    okm = ok[m]
    print(f"\n  {rid} — 신호 {int(keep.sum()):,}건 · 트레일 발동 {int((okm & keep).sum()):,}건"
          f" ({(okm & keep).sum()/keep.sum()*100:.0f}%)")
    # ① 가정 가격 대비 실제 종가가 얼마나 아래였나
    a = px_model[m][okm & keep]; b = px_close[m][okm & keep]; c = px_open1[m][okm & keep]
    d1 = (b / a - 1) * 100; d2 = (c / a - 1) * 100
    d1 = d1[np.isfinite(d1)]; d2 = d2[np.isfinite(d2)]
    print(f"     발동일 종가는 가정보다 중앙 {np.median(d1):+.2f}% · 평균 {d1.mean():+.2f}%"
          f" · 5% 아래꼬리 {np.percentile(d1,5):+.1f}% · 최악 {d1.min():+.1f}%")
    print(f"     다음날 시가는 가정보다 중앙 {np.median(d2):+.2f}% · 평균 {d2.mean():+.2f}%"
          f" · 5% 아래꼬리 {np.percentile(d2,5):+.1f}% · 최악 {d2.min():+.1f}%")

    print(f"     {'청산 가정':<16}{'평균':>8}{'중앙':>8}{'승률':>7}{'하위5%':>9}{'최악':>9}{'-30%↓':>9}")
    for lbl, px in (("가정(지금)", px_model), ("발동일 종가", px_close), ("익일 시가", px_open1)):
        r = (px[m][keep] / buy[keep] - 1) * 100 - cost[keep]
        r = r[np.isfinite(r)]
        print(f"     {lbl:<16}{r.mean():>8.2f}{np.median(r):>8.2f}{(r>0).mean()*100:>6.0f}%"
              f"{np.percentile(r,5):>9.1f}{r.min():>9.1f}{(r<=-30).mean()*100:>8.2f}%")
