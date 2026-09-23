# -*- coding: utf-8 -*-
"""미장 [상승장 신고가](N1) 보유 40 vs 60일 — **규칙 단독 계좌** (2026-09-24).

hold_sweep_us.py 에서 60일이 두 기간 모두 건당 평균·승률이 조금 나았다(+0.88→+1.47 · +1.39→+2.26, 승률 +1%p).
보유가 길면 건당 수익은 저절로 커지므로 hold_solo_kr.py 와 같은 단독 계좌 틀로 판정한다
(최대 10종목 · 10% · 매일 종가 평가 · 무작위 · 30시드 중앙, 기간마다 1.0 에서 시작).
잣대: 폐지 포함 패널(us_full_2007.pkl) · us_surv_measure.py 규칙 정의. 청산 수익은 n{h}, 중간 평가는 원주가.

    python hold_solo_us.py
"""
import io, sys, contextlib, warnings
warnings.filterwarnings("ignore")
sys.argv = [sys.argv[0], "--panel", "us_full_2007.pkl", "--since", "20090101"]
with contextlib.redirect_stdout(io.StringIO()):
    import us_surv_measure as M
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd

K = M.K
C = M.rules(pd.Series(True, index=K.index), "u_all")
SEEDS, SLOTS = 30, 10
PER = (("A 2009~15", "20090101", "20151231"), ("B 2016~", "20160101", "20991231"))
dates = np.array(sorted(K.date.unique()))
tick = np.array(sorted(K.ticker.unique()))
P = np.full((len(dates), len(tick)), np.nan, dtype=np.float32)
P[np.searchsorted(dates, K.date.values), np.searchsorted(tick, K.ticker.values)] = K.rawclose.values
tix = {t: i for i, t in enumerate(tick)}


def trades(cond, h):
    X = K[cond].dropna(subset=[f"n{h}"])
    X = X[X.buy > 0].sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h
        keep.append(ix)
    X = X.loc[keep, ["ticker", "date", f"n{h}"]].rename(columns={f"n{h}": "ret"})
    X["buy"] = K.loc[X.index, "rawclose"].values     # 중간 평가 기준 = 신호일 원주가(분할 착시 방지)
    X["di"] = np.searchsorted(dates, X.date.values)
    return X


def solo(T, h, lo, hi, seed):
    """hold_solo_kr.py 의 solo 와 같다."""
    rng = np.random.default_rng(seed)
    d0, dN = int(np.searchsorted(dates, lo)), int(np.searchsorted(dates, hi, "right")) - 1
    T = T[(T.di >= d0) & (T.di + h <= dN)]
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


print("\n## [상승장 신고가] 보유 40 vs 60 — 규칙 단독 계좌 (10종목·10%·매일평가·30시드 중앙)\n")
print("| 기간 | 보유 | 최종 배수 | 연수익 | 최대낙폭 | 평균 투입 | 손실 해 | 60일이 이긴 시드 |")
print("|---|---|---|---|---|---|---|---|")
T = {h: trades(C["N1"], h) for h in (40, 60)}
for pn, lo, hi in PER:
    R = {h: np.array([solo(T[h], h, lo, hi, s) for s in range(SEEDS)]) for h in (40, 60)}
    w = (R[60][:, 0] > R[40][:, 0]).mean() * 100
    for h in (40, 60):
        m = np.median(R[h], axis=0)
        print(f"| {pn} | {h}일{' (지금)' if h == 40 else ''} | {m[0]:.2f}배 | {m[1]:+.1f}% | {m[2]:.1f}% | {m[3]:.0f}% | "
              f"{m[4]:.0f}/{m[5]:.0f} | {'—' if h == 40 else f'{w:.0f}%'} |", flush=True)
