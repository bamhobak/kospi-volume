# -*- coding: utf-8 -*-
"""H0425 단기과열종목 지정(3거래일 30분 단일가) 전후 — 2026-11-17 "규칙 하나만 더". 등록부에 없던 재료.
사건: KIND '단기과열종목(3거래일 단일가매매) 지정'(보통주, 공시 날 D 저녁 → D+1~D+3 단일가 → D+4 풀림) · '(예고)' 따로.
판: D+1 시가→종가 · D+1 시가→D+3 종가(단일가 동안) · D+3 종가→D+4 시가 · D+4 시가→종가·3·5·10일(풀린 뒤). 대조 = 같은 날 전 종목 평균. 비용 0.23. 학습 16~22 / 검증 23~.
"""
import math, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parent.parent; COST = 0.23
OUT = []; P_ = lambda s="": (OUT.append(s), print(s, flush=True))
t_ = lambda s: s.mean() / s.std(ddof=1) * math.sqrt(len(s)) if len(s) > 2 and s.std(ddof=1) > 0 else 0.0
P = pd.read_pickle(BASE / "research" / "cache" / "factory_px.pkl"); P = P[P.date >= "20151001"]
cal = sorted(P.date.unique()); ci = {d: i for i, d in enumerate(cal)}; tk = sorted(P.ticker.unique()); ti = {t: i for i, t in enumerate(tk)}
W = lambda col: P.pivot(index="date", columns="ticker", values=col).reindex(index=cal, columns=tk).values.astype(np.float64)
OP, CL = W("open"), W("close"); del P; nd, nt = CL.shape
sh = lambda A, k: np.vstack([A[k:], np.full((k, nt), np.nan)])
def fwd(a, b):
    x = (b / a - 1) * 100 - COST; x[(np.abs(x) > 80) | ~np.isfinite(x)] = np.nan; return x
RET = {"D+1 시가→종가": fwd(sh(OP, 1), sh(CL, 1)), "D+1 시가→D+3 종가(단일가 동안)": fwd(sh(OP, 1), sh(CL, 3)), "D+3 종가→D+4 시가": fwd(sh(CL, 3), sh(OP, 4)),
       "D+4 시가→종가(풀린 날)": fwd(sh(OP, 4), sh(CL, 4)), "D+4 시가→3일": fwd(sh(OP, 4), sh(CL, 6)), "D+4 시가→5일": fwd(sh(OP, 4), sh(CL, 8)), "D+4 시가→10일": fwd(sh(OP, 4), sh(CL, 13))}
MK = {k: np.nanmean(np.where((CL >= 1000), v, np.nan), axis=1) for k, v in RET.items()}
R5 = (CL / np.vstack([np.full((5, nt), np.nan), CL[:-5]]) - 1) * 100
c = sqlite3.connect("file:%s?mode=ro" % (BASE / "data" / "dart" / "kind_time.db"), uri=True)
K = pd.read_sql("select day, kcode, market, title from kind where title like '%단기과열종목%'", c); c.close()
K = K[~K.title.str.contains(r"\(.+\)$") | K.title.str.endswith("지정") | K.title.str.endswith("지정예고")]
K["kind"] = np.where(K.title.str.contains("예고"), "예고", np.where(K.title.str.contains("연장"), "연장", np.where(K.title.str.contains("해제"), "해제", "지정")))
K["t"] = K.kcode + "0"; K = K[K.t.isin(ti) & K.day.isin(ci)].drop_duplicates(["day", "t", "kind"])
K["i"] = K.day.map(ci); K["j"] = K.t.map(ti); K = K[CL[K.i.values, K.j.values] >= 1000]
K["r5"] = R5[K.i.values, K.j.values]
P_("# H0425 단기과열종목 지정 전후 (2026-11-17)\n"); P_("종류별 건수: " + str(K.kind.value_counts().to_dict()) + " · 지정 때 5일 등락 중앙 %+.0f%%" % K[K.kind == "지정"].r5.median())
P_("\n| 사건 | 판 | 학습 건 | 건당(중앙·승률) | 날 바구니(t) | 시장 대비(t) | 검증 건 | 건당(중앙·승률) | 날 바구니(t) | 시장 대비(t) |\n|---|---|---|---|---|---|---|---|---|---|")
for kd in ("지정", "예고"):
    Z = K[K.kind == kd].copy()
    for k, A in RET.items():
        Z["r"] = A[Z.i.values, Z.j.values]; Z["m"] = MK[k][Z.i.values]; cells = []
        for a, b in (("20160101", "20221231"), ("20230101", "20991231")):
            z = Z[(Z.day >= a) & (Z.day <= b)].dropna(subset=["r"])
            if len(z) < 20: cells.append("%d | – | – | –" % len(z)); continue
            d = z.groupby("day").r.mean(); e = z.assign(e=z.r - z.m).groupby("day").e.mean()
            cells.append("%d | %+.2f%% (%+.2f·%.0f%%) | %+.2f%% (t%.1f) | %+.2f (t%.1f)" % (len(z), z.r.mean(), z.r.median(), (z.r > 0).mean() * 100, d.mean(), t_(d), e.mean(), t_(e)))
        P_("| %s | %s | %s | %s |" % (kd, k, cells[0], cells[1]))
(BASE / "research" / "reports" / "heat_1117.md").write_text("\n".join(OUT), encoding="utf-8")
