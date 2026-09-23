# -*- coding: utf-8 -*-
"""국내 보유기간 후보를 **규칙 단독 계좌**로 판정한다 (2026-09-24).

hold_sweep_kr.py 에서 [조정매집] 10→20 · [폭락반등] 20→40 · [업종붕괴 이탈] 5→10 · [깊은 이격] 5→10 이
두 기간 모두 건당 평균·승률이 나았다. 그러나 보유가 길면 건당 수익은 날수만큼 저절로 커진다 —
대가는 돈이 오래 묶이는 것이다. 그래서 rule_solo.py 와 **같은 단독 계좌 틀**로 잰다:
최대 10종목 · 종목당 계좌의 10% · 매일 종가 평가 · 같은 날 신호가 자리보다 많으면 무작위 · 30시드 중앙값.
기간 A 2005~2015 · B 2016~ 를 **각각 1.0 에서** 시작한다. 수익 = 청산 종가/매수가 - 비용(hold_sweep_kr 와 같다).

    python hold_solo_kr.py
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
SRC = (BASE / "portfolio.py").read_text(encoding="utf-8")
ns = {"__file__": str(BASE / "portfolio.py")}
_real = sys.stdout
sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(SRC.split("# 신호를 한 표로 모은다", 1)[0], "portfolio.py", "exec"), ns)
sys.stdout = _real
sys.stdout.reconfigure(encoding="utf-8")
RULES = ns["RULES"]
NAME = {"P2": "조정매집", "P3": "폭락반등", "P4": "업종붕괴 이탈", "P6": "깊은 이격"}
CAND = {"P2": (10, 20), "P3": (20, 40), "P4": (5, 10), "P6": (5, 10)}
SEEDS, SLOTS = 30, 10
PER = (("A 2005~15", "20050101", "20151231"), ("B 2016~", "20160101", "20991231"))


def wide(K):
    dates = np.array(sorted(K.date.unique()))
    tick = np.array(sorted(K.ticker.unique()))
    P = np.full((len(dates), len(tick)), np.nan, dtype=np.float32)
    P[np.searchsorted(dates, K.date.values), np.searchsorted(tick, K.ticker.values)] = K.close.values
    return dates, {t: i for i, t in enumerate(tick)}, P


def trades(K, cond, h, dates):
    g = K.groupby("ticker", sort=False)
    X = K[cond.fillna(False)].copy()
    X["exit"] = g.close.shift(-h).reindex(X.index)
    X = X.dropna(subset=["buy", "exit", "cost"])
    X = X[X.buy > 0]
    X["ret"] = (X.exit / X.buy - 1) * 100 - X.cost
    X["di"] = np.searchsorted(dates, X.date.values)
    X = X.sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h
        keep.append(ix)
    return X.loc[keep, ["ticker", "date", "di", "buy", "ret"]]


def solo(T, h, dates, tix, P, lo, hi, seed):
    rng = np.random.default_rng(seed)
    d0, dN = int(np.searchsorted(dates, lo)), int(np.searchsorted(dates, hi, "right")) - 1
    T = T[(T.di >= d0) & (T.di + h <= dN)]          # 기간 안에서 끝나는 거래만
    byd = {k: g for k, g in T.groupby("di")}
    cash, pos, navs, inv = 1.0, [], [], []
    for d in range(d0, dN + 1):
        keep = []
        for p in pos:
            if d >= p[0]:
                cash += p[3] * (1 + p[4] / 100)
            else:
                keep.append(p)
        pos = keep
        val = 0.0
        for ex, ti, buy, alloc, ret in pos:
            px = P[d, ti]
            val += alloc * (px / buy if np.isfinite(px) and px > 0 else 1.0)
        nav = cash + val
        navs.append(nav); inv.append(val / nav if nav > 0 else 0)
        g = byd.get(d)
        if g is None or len(pos) >= SLOTS:
            continue
        held = {p[1] for p in pos}
        for r in g.sample(frac=1, random_state=int(rng.integers(1 << 30))).itertuples():
            if len(pos) >= SLOTS:
                break
            ti = tix.get(r.ticker)
            if ti is None or ti in held:
                continue
            alloc = min(nav / SLOTS, cash)
            if alloc <= nav * 0.01:
                break
            cash -= alloc
            pos.append((d + h, ti, float(r.buy), alloc, float(r.ret)))
            held.add(ti)
    nav = np.array(navs)
    dd = nav / np.maximum.accumulate(nav) - 1
    yrs = len(nav) / 252
    ys = pd.Series(nav, index=[x[:4] for x in dates[d0:dN + 1]]).groupby(level=0).last()
    yr = ys / pd.concat([pd.Series([1.0]), ys.iloc[:-1]]).values - 1
    return nav[-1], (nav[-1] ** (1 / yrs) - 1) * 100, dd.min() * 100, np.mean(inv) * 100, int((yr < 0).sum()), len(yr)


print("\n## 국내 보유 후보 — 규칙 단독 계좌 (10종목·10%·매일평가·30시드 중앙)\n")
print("| 규칙 | 기간 | 보유 | 최종 배수 | 연수익 | 최대낙폭 | 평균 투입 | 손실 해 | 긴 쪽이 이긴 시드 |")
print("|---|---|---|---|---|---|---|---|---|")
cache = {}
for rid, (h0, h1) in CAND.items():
    K, hold, stop, pct, mx, cond = RULES[rid]
    assert hold == h0
    if id(K) not in cache:
        cache[id(K)] = wide(K)
    dates, tix, P = cache[id(K)]
    T = {h: trades(K, cond, h, dates) for h in (h0, h1)}
    for pn, lo, hi in PER:
        R = {h: np.array([solo(T[h], h, dates, tix, P, lo, hi, s) for s in range(SEEDS)]) for h in (h0, h1)}
        w = (R[h1][:, 0] > R[h0][:, 0]).mean() * 100
        for h in (h0, h1):
            m = np.median(R[h], axis=0)
            tag = " (지금)" if h == h0 else ""
            print(f"| [{NAME[rid]}] | {pn} | {h}일{tag} | {m[0]:.2f}배 | {m[1]:+.1f}% | {m[2]:.1f}% | {m[3]:.0f}% | "
                  f"{m[4]:.0f}/{m[5]:.0f} | {'—' if h == h0 else f'{w:.0f}%'} |", flush=True)
