# -*- coding: utf-8 -*-
"""2026-11-14 규칙 손익 해부 — 스윙 9규칙(portfolio.py). 신호표 C:/temp/kp/port_sig.pkl(mix_swing_1114 가 저장)에
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
S = S[S.date >= "20160101"].reset_index(drop=True)
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


B0 = (acct([], d0="20160101", d1="20221231"), acct([], d0="20230101", d1="20261231"))
P("# 스윙 9규칙 손익 해부 (11-14)\n\n- 신호 %d건(2016~) · 기준 계좌(1억·체결 손해·청산 확정) 연 학습 %+.1f%% · 검증 %+.1f%%\n" % (len(X), *B0))
P("| 규칙 | 재료 | 뺄 칸 | 학습: 칸 건당 · 빼면 +%p · 무작위 등수 | 검증: 칸 건당 · 빼면 +%p · 등수 | 계좌 연%p 학습 / 검증 | 판정 |"); P("|---|---|---|---|---|---|---|")
for rid, R in X.groupby("rid"):
    A = R[R.date <= "20221231"]; Bv = R[R.date >= "20230101"]
    if len(A) < 60 or len(Bv) < 20: P("| %s | (표본 부족 학습 %d·검증 %d) | | | | | |" % (rid, len(A), len(Bv))); continue
    rows = []
    for f in FEAT:
        a = A.dropna(subset=[f]); b = Bv.dropna(subset=[f])
        if len(a) < 60 or len(b) < 20: continue
        q1, q2 = a[f].quantile([1 / 3, 2 / 3])
        if q1 == q2: continue
        for cut, lo, hi in (("하위 1/3", -np.inf, q1), ("가운데", q1, q2), ("상위 1/3", q2, np.inf)):
            ma = (a[f] > lo) & (a[f] <= hi); mb = (b[f] > lo) & (b[f] <= hi)
            k, kb = int(ma.sum()), int(mb.sum())
            if k < 15 or k > len(a) - 15 or kb < 5: continue
            gain = a.ret[~ma].mean() - a.ret.mean()
            if gain <= 0: continue
            pt = float((null_gain(a.ret.to_numpy(), k) < gain).mean())
            if pt < P_TR: continue
            gv = b.ret[~mb].mean() - b.ret.mean()
            pv = float((null_gain(b.ret.to_numpy(), kb) < gv).mean()) if gv > 0 else 0.0
            rows.append((f, cut, lo, hi, a.ret[ma].mean(), gain, pt, b.ret[mb].mean(), gv, pv, a.index[ma.to_numpy()], b.index[mb.to_numpy()]))
    rows.sort(key=lambda r: (-r[9], -r[8]))
    if not rows: P("| %s | (학습 99.5%% 넘는 칸 없음 · 학습 %d건) | | | | | |" % (rid, len(A))); continue
    for f, cut, lo, hi, ca, ga, pt, cb, gv, pv, ia, ib in rows[:4]:
        okv = gv > 0 and pv >= P_VA
        if okv:
            da = acct(list(ia), d0="20160101", d1="20221231") - B0[0]; db = acct(list(ib), d0="20230101", d1="20261231") - B0[1]
        else: da = db = float("nan")
        P("| %s | %s(%s) | %s (%s) | %+.2f · %+.2f · %.1f%% | %+.2f · %+.2f · %.0f%% | %s | %s |" % (rid, FT.FEATS[f][0][:22], f, cut,
          "≤%.3g" % hi if cut == "하위 1/3" else (">%.3g" % lo if cut == "상위 1/3" else "%.3g~%.3g" % (lo, hi)), ca, ga, pt * 100, cb, gv, pv * 100,
          ("%+.1f / %+.1f" % (da, db)) if okv else "-", "**후보**" if okv and da > 0 and db > 0 else ("검증 ✅ · 계좌 ❌" if okv else "검증 ❌")))
    print("  %s %.1f분" % (rid, (time.time() - t0) / 60), flush=True)
(ROOT / "reports" / "anatomy_swing_1114.md").write_text("\n".join(OUT), encoding="utf-8")
print("끝 %.1f분" % ((time.time() - t0) / 60))
