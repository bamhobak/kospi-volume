# -*- coding: utf-8 -*-
"""(anatomy_swing_1114 앞부분) 2026-11-14 규칙 손익 해부 — 스윙 9규칙(portfolio.py). 신호표 C:/temp/kp/port_sig.pkl(mix_swing_1114 가 저장)에
공장 재료(FT.FEATS, 신호 날 종가까지 아는 것 — 다음 날 시가에 산다)를 붙여 규칙 × 재료 × 삼등분으로 '어디서 지는가'.
판정은 anatomy_1114 와 같음: 학습 2016~22 무작위 솎기 300번 중 99.5% · 검증 2023~ 같은 방향 90% →
계좌 확인 = portfolio.py 와 같은 자리·비중·우선순위로 굴린 국장 계좌(청산 때 확정, 체결 손해 1억 기준)를 그 칸 빼고 다시 → 학습·검증 연수익이 둘 다 늘어야 후보.
    python research/anatomy_swing_1114.py   → research/reports/anatomy_swing_1114.md"""
import sys, time, math, pickle
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "factory"), str(ROOT)]
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import lab, feats as FT
OUT = []; P = lambda s="": (OUT.append(str(s)), print(s, flush=True))
NR, P_TR, P_VA = 300, 0.995, 0.90
rng = np.random.default_rng(13); t0 = time.time()
Z = pickle.load(open(r"C:\temp\kp\port_sig.pkl", "rb")); S = Z["S"].copy(); dates = Z["dates"]; DI = {d: i for i, d in enumerate(dates)}
S["date"] = S.date.astype(str); S["ticker"] = S.ticker.astype(str)
S["ret"] = (S.exit / S.buy - 1) * 100 - S.cost
S = S[S.date >= "20100101"].reset_index(drop=True)
U = lab.hist()
FEAT = [f for f in FT.FEATS if f in U.columns and f not in FT.FLOW and U[f].dtype.kind in "fi" and f not in S.columns]
X = S.merge(U[["date", "ticker"] + FEAT], on=["date", "ticker"], how="left")
del U
print("신호 %d · 재료 %d · %.1f분" % (len(X), len(FEAT), (time.time() - t0) / 60), flush=True)
imp = lambda p: max(0.0, 0.143 + 1.321 * math.sqrt(p))
X = X.sort_values(["di"]).reset_index(drop=True)


def acct(drop_idx, C=1e8, d0="20160101", d1="20221231"):
    """portfolio.py 자리 규칙 그대로(규칙별 mx · 같은 종목 중복 X · 비중 pct · 계좌 넘으면 안 삼), 청산 때 확정 → 연 %."""
    i0 = DI[min(d for d in dates if d >= d0)]; i1 = DI[max(d for d in dates if d <= d1)]
    Y = X[(X.di >= i0) & (X.di <= i1) & ~X.index.isin(drop_idx)]
    G = {i: g for i, g in Y.groupby("di")}
    eq = C; pos = []
    for i in range(i0, i1 + 1):
        still = []
        for p in pos:
            if p[2] <= i: eq += p[1] * p[3] / 100
            else: still.append(p)
        pos = still
        g = G.get(i)
        if g is None: continue
        inv = sum(p[1] for p in pos)
        for t in g.itertuples():
            w = eq * t.pct / 100
            if sum(1 for p in pos if p[0] == t.rid) >= t.mx or inv + w > eq or any(p[4] == t.ticker for p in pos): continue
            pi = w / (t.amt20 * 1e8) * 100 if t.amt20 and t.amt20 > 0 else 50
            pos.append((t.rid, w, i + t.hold, t.ret - imp(pi), t.ticker)); inv += w
    for p in pos: eq += p[1] * p[3] / 100
    yrs = (i1 - i0 + 1) / 250
    return ((eq / C) ** (1 / yrs) - 1) * 100


def null_gain(r, k):
    m = r.mean(); N = len(r)
    idx = np.argsort(rng.random((NR, N)), axis=1)[:, :k]
    return (r.sum() - r[idx].sum(1)) / (N - k) - m



# ── 홀드아웃 2010~15 (재료 자료가 2010~ — 학습·검증에서 고른 칸을 처음 보는 구간에) ──
CAND = [("P3", "lr50", -0.632, np.inf, "[폭락반등] 50일 기울기 상위 1/3 빼기"), ("P4", "r1t", -4.76, 4.88, "[업종붕괴 이탈?] P4 오늘 등락 가운데 빼기"),
        ("P4", "turn", -np.inf, 0.879, "P4 회전율 하위 1/3 빼기"), ("P6", "kdev", -21.6, np.inf, "P6 코스피 60일선 대비 상위 1/3 빼기"),
        ("P7", "kdev", -np.inf, 2.79, "P7 코스피 60일선 대비 하위 1/3 빼기")]
H0 = acct([], d0="20100101", d1="20151231")
L = ["# 스윙 해부 후보 — 홀드아웃 2010~15 확인 (11-14)", "", "기준 계좌(1억·체결 손해·청산 확정) 2010~15 연 %+.1f%%" % H0, "",
     "| 후보 | 2010~15 그 규칙 건수 | 뺄 칸 건수 · 건당 | 나머지 건당 − 전체 | 계좌 연%p | 판정 |", "|---|---|---|---|---|---|"]
for rid, f, lo, hi, nm in CAND:
    R = X[(X.rid == rid) & (X.date <= "20151231")].dropna(subset=[f])
    m = (R[f] > lo) & (R[f] <= hi)
    g = R.ret[~m].mean() - R.ret.mean() if m.any() and (~m).any() else float("nan")
    da = acct(list(R.index[m.to_numpy()]), d0="20100101", d1="20151231") - H0
    L.append("| %s | %d | %d · %+.2f%% | %+.2f%%p | %+.1f | %s |" % (nm, len(R), int(m.sum()), R.ret[m].mean() if m.any() else float("nan"), g, da,
             "**홀드아웃도 통과**" if g > 0 and da > 0 else "홀드아웃 ❌"))
print(chr(10).join(L))
(ROOT / "reports" / "anatomy_swing_hold_1114.md").write_text(chr(10).join(L), encoding="utf-8")
