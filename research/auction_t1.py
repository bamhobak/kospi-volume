# -*- coding: utf-8 -*-
"""H0317 ⓐ 보강 — T1 후보 '전날' 1분봉을 이벤트 도구로 받아(상위 1,000 밖 소형주 포함) 종가 단일가 쏠림을 다시 잰다.

ca = 전날 종가(15:30 단일가) / 전날 15:19 봉 종가 - 1,  pre = 15:19 / 그 전날 종가 - 1
T1 2022-12~2026-08, 학습 ~2024 · 검증 2025~.
    python research/auction_t1.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "factory"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import lab, feats as FT, common as C
import m1_event as ME

U = lab.hist().sort_values(["ticker", "date"])
P = pd.read_pickle(C.CACHE / "factory_px.pkl").sort_values(["ticker", "date"])
P["pdate"] = P.groupby("ticker").date.shift(1)
P["ppc"] = P.groupby("ticker").close.shift(2)
T = U[U.t1 & U.oc.notna() & (U.date >= "20221202")][["ticker", "date", "oc", "gap"]].merge(P[["ticker", "date", "pdate", "ppc"]], on=["ticker", "date"])
T["ret"] = T.oc.clip(-60, 60) - FT.COST
print("T1 %d건 → 전날 1분봉 받기" % len(T), flush=True)
got, miss = ME.ensure("KR", list(zip(T.ticker, T.pdate)), log=lambda *a: print(*a, flush=True))
print("받음 %d · 못 받음 %d" % (got, miss), flush=True)
ca, pre = [], []
for t, g in T.groupby("ticker"):
    B = ME.bars("KR", t, list(g.pdate))
    for r in g.itertuples():
        b = B.get(r.pdate)
        if b is None or len(b) < 30: ca.append((r.Index, np.nan, np.nan)); continue
        b19 = b[b.hm <= "1519"]
        if not len(b19): ca.append((r.Index, np.nan, np.nan)); continue
        p19 = b19.c.iloc[-1]; cl = b.c.iloc[-1]
        ca.append((r.Index, (cl / p19 - 1) * 100, (p19 / r.ppc - 1) * 100))
X = pd.DataFrame(ca, columns=["i", "ca", "pre"]).set_index("i")
T = T.join(X)
T.to_pickle(C.CACHE / "auction_t1.pkl")
print("ca 있는 T1 %d / %d" % (T.ca.notna().sum(), len(T)))


def f(s):
    return ("%5d %+6.2f %4.1f%% t%4.1f" % (s["n"], s["mean"], s["win"], s["t"])) if s else "    0      -"


def row(nm, m):
    a = lab.stats(T[m & (T.date <= "20241231")]); b = lab.stats(T[m & (T.date >= "20250101")])
    print("%-44s | 학습 %s | 검증 %s" % (nm, f(a), f(b)), flush=True)


h = T.ca.notna()
row("T1 (전날 1분봉 있음)", h)
for lo, hi in ((-99, -1), (-1, -0.3), (-0.3, 0.3), (0.3, 1), (1, 99)):
    row("전날 단일가 %+.1f < ca ≤ %+.1f" % (lo, hi), h & (T.ca > lo) & (T.ca <= hi))
row("전날 15:19까지 -1%↑ & 단일가 ≤ -1", h & (T.pre > -1) & (T.ca <= -1))
row("전날 15:19까지 -1%↑ & 단일가 ≤ -0.5", h & (T.pre > -1) & (T.ca <= -0.5))
row("전날 단일가 ≤ -0.5 (그 밖 대조: > -0.5)", h & (T.ca <= -0.5))
row("전날 단일가 > -0.5", h & (T.ca > -0.5))
