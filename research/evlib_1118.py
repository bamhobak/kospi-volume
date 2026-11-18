# -*- coding: utf-8 -*-
"""사건 연구 공용(2026-11-18, 코덱스 제안 2·6번 실측) — research/heat_1117.py 틀 그대로.
가격 = research/cache/factory_px.pkl(2009~, 폐지 포함 3,864종목, 시가·종가). 비용 0.23. 학습 16~22 / 검증 23~."""
import math, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parent.parent; COST = 0.23
OUT = []
def P_(s=""):
    OUT.append(s); print(s, flush=True)
def t_(s):
    s = pd.Series(s).dropna()
    return s.mean() / s.std(ddof=1) * math.sqrt(len(s)) if len(s) > 2 and s.std(ddof=1) > 0 else 0.0

P = pd.read_pickle(BASE / "research" / "cache" / "factory_px.pkl"); P = P[P.date >= "20150601"]
cal = sorted(P.date.unique()); ci = {d: i for i, d in enumerate(cal)}; tk = sorted(P.ticker.unique()); ti = {t: i for i, t in enumerate(tk)}
calA = np.array(cal)
W = lambda col: P.pivot(index="date", columns="ticker", values=col).reindex(index=cal, columns=tk).values.astype(np.float64)
OP, CL = W("open"), W("close"); del P; nd, nt = CL.shape
def sh(A, k):
    if k == 0: return A
    if k > 0: return np.vstack([A[k:], np.full((k, nt), np.nan)])
    return np.vstack([np.full((-k, nt), np.nan), A[:k]])
def fwd(a, b, cost=COST):
    x = (b / a - 1) * 100 - cost; x[(np.abs(x) > 150) | ~np.isfinite(x)] = np.nan; return x
BIG = CL >= 1000
def mkt(A):
    return np.nanmean(np.where(BIG, A, np.nan), axis=1)
def on_or_before(day):
    """그 날짜 이하 마지막 거래일 색인(없으면 -1)."""
    return int(np.searchsorted(calA, day, side="right")) - 1
def after(day):
    """그 날짜보다 뒤 첫 거래일 색인."""
    return int(np.searchsorted(calA, day, side="right"))
SPLIT = (("학습 16~22", "20160101", "20221231"), ("검증 23~", "20230101", "20991231"))
def cell(z, rcol="r", mcol="m", minn=15):
    """건수 | 건당 평균(중앙·승률) | 날 바구니(t) | 시장 대비(t)"""
    z = z.dropna(subset=[rcol])
    if len(z) < minn: return "%d | – | – | –" % len(z)
    d = z.groupby("day")[rcol].mean(); e = (z[rcol] - z[mcol]).groupby(z.day).mean()
    return "%d | %+.2f%% (%+.2f·%.0f%%) | %+.2f%% (t%.1f) | %+.2f (t%.1f)" % (len(z), z[rcol].mean(), z[rcol].median(), (z[rcol] > 0).mean() * 100, d.mean(), t_(d), e.mean(), t_(e))
def both(Z, rcol="r", mcol="m"):
    return " | ".join(cell(Z[(Z.day >= a) & (Z.day <= b)], rcol, mcol) for _, a, b in SPLIT)
HEAD = "| 학습 건 | 건당(중앙·승률) | 날 바구니(t) | 시장 대비(t) | 검증 건 | 건당(중앙·승률) | 날 바구니(t) | 시장 대비(t) |"
def nodup(Z, gap):
    """같은 종목이 보유 기간(gap 거래일) 안에 또 나오면 뒤엣것을 버린다."""
    Z = Z.sort_values(["j", "i"]); keep = []; last = {}
    for i, j in zip(Z.i.values, Z.j.values):
        ok = j not in last or i - last[j] >= gap
        keep.append(ok)
        if ok: last[j] = i
    return Z[np.array(keep)]
def save(name):
    (BASE / "research" / "reports" / name).write_text("\n".join(OUT) + "\n", encoding="utf-8")
