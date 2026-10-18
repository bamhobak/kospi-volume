# -*- coding: utf-8 -*-
"""H0360 지수 덮개 — 띠(±0/2/3%) × 비중(30/50%) 계좌 비교, 다음날 시가 체결 (2026-10-18)."""
import sys
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "research"))
import numpy as np, pandas as pd
import FinanceDataReader as fdr
import ideas5_1018 as I5


def state(c, ma, band):
    m = pd.Series(c).rolling(ma).mean().values
    s = np.zeros(len(c), bool); inpos = False
    for i in range(len(c)):
        if np.isnan(m[i]): continue
        if not inpos and c[i] > m[i] * (1 + band / 100): inpos = True
        elif inpos and c[i] < m[i] * (1 - band / 100): inpos = False
        s[i] = inpos
    return s


def main():
    ns = I5.portfolio_ns()
    C = ns["simulate"](1.0, 1.0, quiet=True)[0]
    X = fdr.DataReader("KS200", "2004-01-01"); X = X[X.Close > 0]
    X.loc[X.Open <= 0, "Open"] = np.nan; X["Open"] = X.Open.fillna(X.Close.shift(1))
    X["date"] = X.index.strftime("%Y%m%d")
    c, o = X.Close.values, X.Open.values; pc = np.r_[np.nan, c[:-1]]
    C["ra"] = C.nav.pct_change().fillna(0); C["cash"] = (1 - C.expo.shift(1).fillna(0)).clip(0, 1)
    print("| 판 | 최종 | 연 | 최대 낙폭 | 수익 난 해 | 최악의 해 | 2008 | 2011 | 2018 | 2022 |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for nm, band, w in (("지금(덮개 없음)", 0, 0), ("60일선 · 30%", 0, 0.3), ("60일선 · 50%", 0, 0.5), ("±2% 띠 · 30%", 2, 0.3), ("±3% 띠 · 30%", 3, 0.3), ("±3% 띠 · 50%", 3, 0.5)):
        s = state(c, 60, band)
        on = np.r_[False, s[:-1]]; prev = np.r_[False, on[:-1]]
        r = np.where(on & ~prev, c / o - 1, np.where(on & prev, c / pc - 1, np.where(~on & prev, o / pc - 1, 0.0)))
        Y = pd.DataFrame({"date": X.date, "r": np.nan_to_num(r), "sw": (on != prev).astype(float)})
        D = C.merge(Y, on="date", how="left").fillna(0)
        rr = D.ra + D.cash * w * D.r - D.sw * D.cash * w * 0.001
        nav = (1 + rr).cumprod(); yrs = len(nav) / 252
        yr = pd.Series(nav.values, index=D.date.str[:4].values).groupby(level=0).agg(lambda v: v.iloc[-1] / v.iloc[0] - 1) * 100
        print("| %s | %.2f배 | %+.1f%% | %.1f%% | %d/%d | %+.1f%% | %+.1f | %+.1f | %+.1f | %+.1f |" % (
            nm, nav.iloc[-1], (nav.iloc[-1] ** (1 / yrs) - 1) * 100, ((nav / nav.cummax()) - 1).min() * 100, (yr > 0).sum(), len(yr), yr.min(),
            yr.get("2008", np.nan), yr.get("2011", np.nan), yr.get("2018", np.nan), yr.get("2022", np.nan)), flush=True)


if __name__ == "__main__":
    main()
