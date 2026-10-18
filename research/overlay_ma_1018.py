# -*- coding: utf-8 -*-
"""[지수 덮개] 이동평균 길이 비교 — 20·30·60일선 × 띠 0·2·3% (2026-10-18 사용자 "20일선 30일선도 테스트").
① 덮개 단독(코스피200, 다음날 시가 체결, 왕복 0.1%): 연 매매·승률·건당·보유일·연 수익·최대 연속 손실·최악의 해
② 계좌(9규칙 2005~)에 덮개 50%: 최종·연·낙폭·수익 난 해·최악의 해 · 하락 해 2008·2011·2018·2022
    python research/overlay_ma_1018.py
"""
import sys
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "research"))
import numpy as np, pandas as pd
import FinanceDataReader as fdr

GRID = [(m, b) for m in (20, 30, 60) for b in (0, 2, 3)]


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
    X = fdr.DataReader("KS200", "2004-01-01"); X = X[X.Close > 0]
    X.loc[X.Open <= 0, "Open"] = np.nan; X["Open"] = X.Open.fillna(X.Close.shift(1))
    X["date"] = X.index.strftime("%Y%m%d")
    c, o = X.Close.values, X.Open.values; pc = np.r_[np.nan, c[:-1]]
    print("## ① 덮개 단독 — 코스피200 (다음날 시가 체결 · 왕복 0.1%)")
    print("| 판 | 연 매매 | 승률 | 건당 | 이긴 건 | 진 건 | 보유일 | 연 수익 | 최대 연속 손실 | 최악의 해 |"); print("|---|---|---|---|---|---|---|---|---|---|")
    yrs = (len(c) - 60) / 252
    for ma, band in GRID:
        s = state(c, ma, band); tr = []; inpos = False
        for i in range(60, len(c) - 1):
            if not inpos and s[i]: ent, ei = o[i + 1], i + 1; inpos = True
            elif inpos and not s[i]: tr.append(((o[i + 1] / ent - 1) * 100 - 0.1, i + 1 - ei, X.date.iat[ei][:4])); inpos = False
        T = pd.DataFrame(tr, columns=["r", "d", "y"])
        mx = k = 0
        for r in T.r: k = k + 1 if r <= 0 else 0; mx = max(mx, k)
        yr = T.groupby("y").r.apply(lambda v: ((1 + v / 100).prod() - 1) * 100)
        tot = (1 + T.r / 100).prod()
        print("| %d일선 ±%d%% | %.1f | %.0f%% | %+.2f%% | %+.1f%% | %+.1f%% | %.0f | %+.1f%% | %d번 | %+.1f%% |" % (
            ma, band, len(T) / yrs, (T.r > 0).mean() * 100, T.r.mean(), T.r[T.r > 0].mean(), T.r[T.r <= 0].mean(), T.d.mean(), (tot ** (1 / yrs) - 1) * 100, mx, yr.min()), flush=True)
    bh = c[-1] / c[60]; print("(그냥 보유 연 %+.1f%%)" % ((bh ** (1 / yrs) - 1) * 100))

    import ideas5_1018 as I5
    ns = I5.portfolio_ns()
    C = ns["simulate"](1.0, 1.0, quiet=True)[0]
    C["ra"] = C.nav.pct_change().fillna(0); C["cash"] = (1 - C.expo.shift(1).fillna(0)).clip(0, 1)
    print("\n## ② 계좌(9규칙 2005~)에 덮개 50%")
    print("| 판 | 최종 | 연 | 최대 낙폭 | 수익 난 해 | 최악의 해 | 2008 | 2011 | 2018 | 2022 |"); print("|---|---|---|---|---|---|---|---|---|---|")
    for nm, ma, band, w in [("지금(덮개 없음)", 60, 0, 0.0)] + [("%d일선 ±%d%%" % (m, b), m, b, 0.5) for m, b in GRID]:
        s = state(c, ma, band)
        on = np.r_[False, s[:-1]]; prev = np.r_[False, on[:-1]]
        r = np.where(on & ~prev, c / o - 1, np.where(on & prev, c / pc - 1, np.where(~on & prev, o / pc - 1, 0.0)))
        Y = pd.DataFrame({"date": X.date, "r": np.nan_to_num(r), "sw": (on != prev).astype(float)})
        D = C.merge(Y, on="date", how="left").fillna(0)
        rr = D.ra + D.cash * w * D.r - D.sw * D.cash * w * 0.001
        nav = (1 + rr).cumprod(); yrs2 = len(nav) / 252
        yr = pd.Series(nav.values, index=D.date.str[:4].values).groupby(level=0).agg(lambda v: v.iloc[-1] / v.iloc[0] - 1) * 100
        print("| %s | %.2f배 | %+.1f%% | %.1f%% | %d/%d | %+.1f%% | %+.1f | %+.1f | %+.1f | %+.1f |" % (
            nm, nav.iloc[-1], (nav.iloc[-1] ** (1 / yrs2) - 1) * 100, ((nav / nav.cummax()) - 1).min() * 100, (yr > 0).sum(), len(yr), yr.min(),
            yr.get("2008", np.nan), yr.get("2011", np.nan), yr.get("2018", np.nan), yr.get("2022", np.nan)), flush=True)


if __name__ == "__main__":
    main()
