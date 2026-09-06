# -*- coding: utf-8 -*-
"""후보안 3단계 — 부트스트랩 신뢰구간과 '규칙만 갈아 끼운 계좌'.

2단계에서 두 후보가 남았다.
  [폭락반등]  20일낙폭 -20% → -25% (+ 보유 20→15일 안도 있음): 12승4패 → 12승2패 / 13승1패
  [낙폭과대]  20일낙폭 -20% → -30%: 12승1패 → 10승0패
둘 다 신호가 20~40% 줄어든다. 규칙 단위로 좋아 보여도 계좌에서는 진 적이 여러 번 있어
(2026-09-05 공매도×프로그램) 반드시 돈으로 확인한다.
① 월블록 부트스트랩 CI — 우연인가
② 계좌 시뮬 — 규칙 하나만 갈아 끼우고 21년, 그리고 구간별로 비교
사용: IX_FROM=2004-06-01 DART_FROM=20040101 PANEL_KP=panel_kp.pkl PANEL_KQ=panel_kq.pkl python why_lose3.py
"""
import io, os, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES = ns["KP"], ns["KQ"], ns["RULES"]
for P in (KP, KQ):
    g = P.groupby("ticker", sort=False)
    for h in (15,):
        if f"n{h}" not in P.columns: P[f"n{h}"] = (g.close.shift(-h)/P.buy-1)*100 - P.cost

def trades(P, cond, hold, stop):
    gg = P.groupby("ticker", sort=False)
    if stop:
        low = pd.concat([gg.low.shift(-i) for i in range(hold)], axis=1).min(axis=1)
        r = np.where((low <= P.buy*(1-stop)).fillna(False), -stop*100 - P.cost, P[f"n{hold}"])
    else: r = P[f"n{hold}"].values
    m = cond.fillna(False); X = P[m].copy(); X["_r"] = r[m.values]; X = X.dropna(subset=["_r"])
    d = sorted(P.date.unique()); di = {x: i for i, x in enumerate(d)}
    X["di"] = X.date.map(di); X = X.sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i+hold; keep.append(ix)
    return X.loc[keep]

def ci(Z, n=2000, seed=0):
    """월 블록 부트스트랩 — 같은 달 신호는 함께 움직이므로 달 단위로 다시 뽑는다."""
    rng = np.random.default_rng(seed); mo = Z.date.str[:6].values
    grp = [Z._r.values[mo == m] for m in np.unique(mo)]
    k = len(grp)
    out = [np.concatenate([grp[i] for i in rng.integers(0, k, k)]).mean() for _ in range(n)]
    return np.percentile(out, 5), np.percentile(out, 95)

CAND = [
    ("P3", "[폭락반등] 현행", KP, RULES["P3"][5], 20, None),
    ("P3", "[폭락반등] -25%", KP, RULES["P3"][5] & (KP.ret20 <= -25), 20, None),
    ("P3", "[폭락반등] -25%·15일", KP, RULES["P3"][5] & (KP.ret20 <= -25), 15, None),
    ("D1", "[낙폭과대] 현행", KQ, RULES["D1"][5], 20, None),
    ("D1", "[낙폭과대] -25%", KQ, RULES["D1"][5] & (KQ.ret20 <= -25), 20, None),
    ("D1", "[낙폭과대] -30%", KQ, RULES["D1"][5] & (KQ.ret20 <= -30), 20, None),
]
print("① 부트스트랩 90% 신뢰구간 (월 블록 · 2000회)")
print(f"  {'안':<24}{'전체':>18}{'2018~22 학습':>20}{'2023~26 검증':>20}{'붐제외(<2025)':>20}")
print("  " + "-"*104)
for rid, nm, P, cond, hold, stop in CAND:
    Z = trades(P, cond, hold, stop)
    row = ""
    for lo, hi in (("19000101","20991231"), ("20180101","20221231"),
                   ("20230101","20991231"), ("19000101","20241231")):
        z = Z[(Z.date >= lo) & (Z.date <= hi)]
        if len(z) < 8: row += f"{'부족':>20}"; continue
        a, b = ci(z); row += f"{z._r.mean():+6.1f} [{a:+5.1f},{b:+5.1f}]"
    print(f"  {nm:<24}{row}")
