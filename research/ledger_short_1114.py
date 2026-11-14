# -*- coding: utf-8 -*-
"""2026-11-14 장부 모형 덧대기 후속 — 폭락형 스윙 규칙 여럿(P3·P4·P5·P6·D1·D2)에서 되풀이된 칸
'공매도 평균 단가 대비 덜 빠진 1/3(uw_s 상위 1/3) 빼기'를 **한 가설**로(규칙마다 칸 경계는 학습 2017~22 거래로) 계좌에서 잰다.
계좌 = portfolio.py 자리·비중(1억·청산 확정·체결 손해). 구간: 학습 2017~22(공매도 잔고 2016-06~) · 검증 2023~ · 검증 앞뒤 반(2023~24 / 2025~).
뒤집은 짝(하위 1/3 빼기)·무작위 1/3 빼기(같은 수, 50번)도 같이.
    python research/memguard.py research/ledger_short_1114.py"""
import sys, math, pickle
from pathlib import Path
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
Zs = pickle.load(open("C:/temp/kp/port_sig.pkl", "rb")); S = Zs["S"].copy(); dates = Zs["dates"]; DI = {d: i for i, d in enumerate(dates)}
S["date"] = S.date.astype(str); S["ticker"] = S.ticker.astype(str); S["ret"] = (S.exit / S.buy - 1) * 100 - S.cost
L = pd.read_pickle("C:/temp/kp/ledger_1114.pkl")[["ticker", "date", "uw_s"]]; L["ticker"] = L.ticker.astype(str); L["date"] = L.date.astype(str)
X = S[S.date >= "20170101"].merge(L, on=["ticker", "date"], how="left").sort_values("di").reset_index(drop=True)
imp1 = lambda p: max(0.0, 0.143 + 1.321 * math.sqrt(p))
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
            pos.append((t.rid, w, i + t.hold, t.ret - imp1(pi), t.ticker)); inv += w
    for p in pos: eq += p[1] * p[3] / 100
    yrs = (i1 - i0 + 1) / 250
    return ((eq / C) ** (1 / yrs) - 1) * 100



CRASH = ["P3", "P4", "P5", "P6", "D1", "D2"]
TH = {}
for r in CRASH:
    a = X[(X.rid == r) & (X.date <= "20221231")].uw_s.dropna()
    TH[r] = (a.quantile(1 / 3), a.quantile(2 / 3)) if len(a) >= 30 else None
print("규칙별 경계(하위 1/3·상위 1/3):", {k: (round(v[0], 1), round(v[1], 1)) if v else None for k, v in TH.items()})
hi = np.zeros(len(X), bool); lo = np.zeros(len(X), bool)
for r, t in TH.items():
    if t is None: continue
    m = (X.rid == r).to_numpy(); u = X.uw_s.to_numpy()
    hi |= m & (u > t[1]); lo |= m & (u <= t[0])
PER = (("학습 2017~22", "20170101", "20221231"), ("검증 2023~", "20230101", "20261231"), ("검증 앞 2023~24", "20230101", "20241231"), ("검증 뒤 2025~", "20250101", "20261231"))
B = {nm: acct([], d0=a, d1=b) for nm, a, b in PER}
rng = np.random.default_rng(5)
cr = X.rid.isin(CRASH).to_numpy() & X.uw_s.notna().to_numpy()
rows = ["| 판 | " + " | ".join(p[0] for p in PER) + " | 뺀 건수 |", "|---" * (len(PER) + 2) + "|",
        "| 기준(안 뺌) | " + " | ".join("%+.1f%%" % B[p[0]] for p in PER) + " | 0 |"]
for lab_, m in (("**공매도 덜 빠진 1/3 빼기(상위)**", hi), ("뒤집은 짝: 공매도 많이 빠진 1/3 빼기(하위)", lo)):
    idx = list(X.index[m])
    rows.append("| %s | " % lab_ + " | ".join("%+.1f%%p" % (acct(idx, d0=a, d1=b) - B[nm]) for nm, a, b in PER) + " | %d |" % len(idx))
R = []
for _ in range(50):
    pick = rng.random(len(X)) < (hi.sum() / max(cr.sum(), 1))
    idx = list(X.index[pick & cr]); R.append([acct(idx, d0=a, d1=b) - B[nm] for nm, a, b in PER])
R = np.array(R)
rows.append("| 무작위 같은 비율 빼기 50번 평균 (상위 5%%) | " + " | ".join("%+.1f (%+.1f)" % (R[:, j].mean(), np.quantile(R[:, j], 0.95)) for j in range(len(PER))) + " | ~%d |" % hi.sum())
print(chr(10).join(rows))
Path("C:/vscode/kospi-volume/research/reports/ledger_short_1114.md").write_text("# 공매도 장부 — 폭락형 스윙 규칙 덧대기 한 가설 (11-14)" + chr(10) * 2 + chr(10).join(rows), encoding="utf-8")
