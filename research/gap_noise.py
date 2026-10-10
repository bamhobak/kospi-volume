# -*- coding: utf-8 -*-
"""T1 예상가 오차 시험 (2026-10-11 — "엣지(건당 +1%)와 예상가 오차(1%p)가 같은 크기" 지적 확인).

연구 T1 은 실제 시가 갭으로 고르지만, 실전은 08:52 예상가(NXT 장전 체결가·호가)로 고른다. 데이 기록(log.csv)
3일치 예상 갭 오차는 평균 절대 1.0~1.2%p. → 과거 갭에 같은 크기의 오차(라플라스, 평균 절대 = b)를 섞어
'틀린 갭으로 고르고 실제 시가→종가를 받는' T1 을 20번씩 돌려 본다. 문턱을 더 깊게(-2.5·-3) 잡으면 버티는지도.
    python research/gap_noise.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "factory"))
import numpy as np, pandas as pd
import lab, feats as FT

U = lab.hist()
U = U[U.oc.notna() & U.gap.notna()][["ticker", "date", "gap", "q_vm", "liq", "oc", "t1"]].reset_index(drop=True)
U["ret"] = U.oc.astype(float).clip(-60, 60) - FT.COST
TR, VA = lab.TR, lab.VA
dcode = pd.factorize(U.date)[0]


def pick(gap, thr=-2.0):
    g = pd.Series(gap)
    q = g.groupby(dcode).rank(pct=True).values
    med = g.groupby(dcode).transform("median").values
    return (q <= 0.10) & (U.q_vm.values <= 0.30) & (U.liq.values <= 1 / 3) & (gap - med <= thr)


def st(m):
    out = []
    for a, b in (TR, VA):
        T = U[m & (U.date >= a) & (U.date <= b)]
        s = lab.stats(T)
        out.append((s["n"], s["mean"], s["win"], s["t"]) if s else (0, np.nan, np.nan, np.nan))
    return out


def fmt(o):
    return "%5d %+5.2f %4.1f%% t%4.1f" % o


base = pick(U.gap.values)
print("오차 없음(연구 T1)            | 학습 %s | 검증 %s" % tuple(fmt(o) for o in st(base)), flush=True)
rng = np.random.default_rng(7)
for b in (0.5, 1.1, 2.0):
    for thr in (-2.0, -2.5, -3.0):
        R = []
        for k in range(20):
            m = pick(U.gap.values + rng.laplace(0, b, len(U)), thr)
            R.append([x for o in st(m) for x in o] + [(m & base).sum() / max(m.sum(), 1) * 100])
        R = np.array(R)
        mu = R.mean(0)
        print("오차 b=%.1f %%p · 문턱 %+.1f     | 학습 %5d %+5.2f %4.1f%% t%4.1f | 검증 %5d %+5.2f %4.1f%% t%4.1f | 연구 T1 과 겹침 %.0f%% · 검증 평균 범위 %+.2f~%+.2f" % (
            b, thr, *mu[:8], mu[8], R[:, 5].min(), R[:, 5].max()), flush=True)
