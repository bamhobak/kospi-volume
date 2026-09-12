# -*- coding: utf-8 -*-
"""트레일링 -8% 가 최악을 얼마나 막아주나 (2026-09-12).

worst_trades.py 에서 트레일 규칙(P1·P4·P6)의 최악이 -8.4~-9.2% 로 딱 막혀 있었다.
그게 **트레일링 덕분인지** 아니면 **패널을 수리해서 원래 그 정도인지** 를 가른다.
같은 신호를 트레일 없이(정해진 날 종가 청산) 다시 재면 된다.

    python trail_worth.py
"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd

exec(open("portfolio.py", encoding="utf-8").read(), globals())

print("\n" + "=" * 96)
print("트레일 -8% 있을 때 vs 없을 때 — 같은 신호, 청산만 다르게")
print("=" * 96)
print(f"  {'규칙':<5}{'청산':<12}{'신호':>7}{'평균':>8}{'중앙':>8}{'승률':>7}{'하위5%':>9}{'최악':>9}{'-30%↓':>9}")

for rid in ["P1", "P4", "P6"]:
    K, hold, stop, pct, mx, cond = RULES[rid]
    g = K.groupby("ticker", sort=False)
    m = cond.fillna(False)
    X = K[m].copy()
    plain = g.close.shift(-hold).reindex(X.index)          # 트레일 없이 만기 종가 청산
    for lbl, ex in (("트레일 -8%", S[S.rid == rid].set_index(S[S.rid == rid].index).exit),
                    ("없음(만기)", plain)):
        if lbl.startswith("트레일"):
            z = S[S.rid == rid].copy()
            r = (z.exit / z.buy - 1) * 100 - z.cost
        else:
            z = X.dropna(subset=["buy", "cost"]).copy()
            z = z[z.buy > 0]
            r = (plain.reindex(z.index) / z.buy - 1) * 100 - z.cost
            r = r.dropna()
        print(f"  {rid if lbl.startswith('트레일') else '':<5}{lbl:<12}{len(r):>7,}{r.mean():>8.2f}"
              f"{r.median():>8.2f}{(r>0).mean()*100:>6.0f}%{r.quantile(0.05):>9.1f}"
              f"{r.min():>9.1f}{(r<=-30).mean()*100:>8.2f}%")
    print()
