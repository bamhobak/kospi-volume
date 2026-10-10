# -*- coding: utf-8 -*-
"""B 시가 체결량 지도 (H0322, 2026-10-11) — [갭 하락 조용주](T1) 후보를 그날 09:01 봉(시가 단일가+첫 1분) 거래대금으로 나눈다.

ov = 09:01 봉 거래대금 ÷ 20일 평균 하루 거래대금 (%) — 진짜 투매(시가에 물량이 쏟아짐) vs 호가만 비어 찍힌 갭.
살 수 있는 양: 09:01 봉 거래대금의 5% 를 우리 몫으로 볼 때 몇 원까지.
T1 2022-12~2026-08 (그날 1분봉은 m1_event 로 받음), 학습 ~2024 · 검증 2025~.
    python research/t1_openvol.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "factory"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import lab, feats as FT, common as C
import m1_event as ME

U = lab.hist()
T = U[U.t1 & U.oc.notna() & (U.date >= "20221201")][["ticker", "date", "oc", "gap", "amt20", "tr_pred"]].copy()
T["ret"] = T.oc.clip(-60, 60) - FT.COST
got, miss = ME.ensure("KR", list(zip(T.ticker, T.date)), log=lambda *a: print(*a, flush=True))
print("T1 %d건 · 1분봉 받음 %d · 못 받음 %d" % (len(T), got, miss), flush=True)
ov, amt1 = [], []
for t, g in T.groupby("ticker"):
    B = ME.bars("KR", t, list(g.date))
    for r in g.itertuples():
        b = B.get(r.date)
        if b is None or not len(b) or b.hm.iloc[0] > "0902":
            ov.append((r.Index, np.nan, np.nan)); continue
        a1 = float(b.o.iloc[0] * b.v.iloc[0])
        ov.append((r.Index, a1 / r.amt20 * 100 if r.amt20 else np.nan, a1))
X = pd.DataFrame(ov, columns=["i", "ov", "a1"]).set_index("i")
T = T.join(X)
T.to_pickle(C.CACHE / "t1_openvol.pkl")
h = T.ov.notna()
print("09:01 봉 있는 T1 %d / %d · ov 분포: 10%% %.2f · 중앙 %.2f · 90%% %.2f (%%) · 09:01 봉 거래대금 중앙 %.0f만원" % (
    h.sum(), len(T), *T.ov.quantile([.1, .5, .9]), T.a1.median() / 1e4))


def f(s):
    return ("%5d %+6.2f %4.1f%% t%4.1f" % (s["n"], s["mean"], s["win"], s["t"])) if s else "    0      -"


def row(nm, m):
    a = lab.stats(T[m & (T.date <= "20241231")]); b = lab.stats(T[m & (T.date >= "20250101")])
    print("%-40s | 학습 %s | 검증 %s" % (nm, f(a), f(b)), flush=True)


row("T1 (09:01 봉 있음)", h)
qs = T.ov.quantile([.2, .4, .6, .8]).values
edges = [-1, *qs, 1e9]
for i in range(5):
    row("ov 5분위 %d (%.2f~%.2f%%)" % (i + 1, max(edges[i], 0), min(edges[i + 1], 999)), h & (T.ov > edges[i]) & (T.ov <= edges[i + 1]))
row("09:01 봉 거래대금 1천만원↓", h & (T.a1 < 1e7))
row("09:01 봉 거래대금 1천만~5천만원", h & (T.a1 >= 1e7) & (T.a1 < 5e7))
row("09:01 봉 거래대금 5천만원↑", h & (T.a1 >= 5e7))
print("\n살 수 있는 양(09:01 봉 거래대금의 5%%): 중앙 %.0f만원 · 하위 25%% %.0f만원 · 150만원 이상 되는 날 %.0f%%" % (
    T.a1.median() * 0.05 / 1e4, T.a1.quantile(.25) * 0.05 / 1e4, (T.a1 * 0.05 >= 1.5e6).mean() * 100))
