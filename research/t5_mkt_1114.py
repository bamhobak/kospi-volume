# -*- coding: utf-8 -*-
"""2026-11-14 사용자 "최근은 장이 너무 안 좋아서 그런 거 같은데" — [장전 되돌림] 새 날(10-09~11-03) 부진이 장 탓인가.
옛 기간(2025-04~2026-10-08)에서 장이 나빴던 날 규칙 성적을 보고, 장 상태로 맞춘 기대치와 새 날 실제를 비교.
장 상태(그날 전 종목 중앙): 당일 등락(종가÷어제 종가) · 직전 20일 누적 · 장전(08:40) 중앙 · KRX 시가 갭 · 08:40→시가
    python research/t5_mkt_1114.py   (패널 C:/temp/kp/t5_full_panel_1114.pkl ← t5_full_1114.py)"""
import sys, glob
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))
S = pd.read_pickle(r"C:\temp\kp\t5_full_panel_1114.pkl")
K = pd.read_parquet(ROOT / "cache" / "m1_daysum.parquet", columns=["t", "d", "o", "c"]); K["t"] = K.t.astype(str); K["d"] = K.d.astype(str)
K = K[K.d >= "20250101"]; ks = []
for f in sorted(glob.glob(str(BASE / "data/m1/KR/day/*.parquet"))):
    d = Path(f).stem
    if d <= K.d.max(): continue
    x = pd.read_parquet(f, columns=["t", "ts", "o", "c", "v"]); x = x[x.v > 0].sort_values("ts")
    g = x.groupby("t").agg(o=("o", "first"), c=("c", "last")).reset_index(); g["d"] = d; ks.append(g)
K = pd.concat([K] + ks, ignore_index=True).sort_values(["t", "d"])
K["pc"] = K.groupby("t").c.shift(1)
K["r"] = (K.c / K.pc - 1) * 100; K["g"] = (K.o / K.pc - 1) * 100
K = K[K.r.abs() < 30]
M = K.groupby("d").agg(mday=("r", "median"), mgap=("g", "median"), up=("r", lambda x: (x > 0).mean() * 100))
M["m20"] = M.mday.rolling(20).sum().shift(1)                     # 직전 20일(그날 아침에 아는 값)
S["o840"] = (S.o / S.pT - 1) * 100
M = M.join(S.groupby("d").agg(mpre=("mpre", "first"), m840=("o840", "median")))
R = S[(S.rpre <= -3) & (S.cum <= 1_019_060_000) & (S.rk <= 4) & (S.nsig < 10) & S.r_vwhs.notna()].drop(columns=["mpre"]).merge(M, left_on="d", right_index=True)
old = R[(R.d >= "20250401") & (R.d <= "20261008")]; new = R[(R.d >= "20261009") & (R.d <= "20261103")]
mo = M[(M.index >= "20250401") & (M.index <= "20261008")]; mn = M[(M.index >= "20261009") & (M.index <= "20261103")]
P("# [장전 되돌림] 최근 부진이 장 탓인가 (11-14)\n")
P("## 장 상태 — 옛 기간 vs 새 날(10-09~11-03), 전 종목 중앙\n")
P("| 지표 | 옛 기간 평균 | 새 날 평균 | 새 날이 옛 기간 몇 %% 자리 |"); P("|---|---|---|---|")
for c, nm in (("mday", "당일 등락"), ("up", "오른 종목 비율"), ("m20", "직전 20일 누적"), ("mpre", "장전 08:40 중앙"), ("mgap", "KRX 시가 갭"), ("m840", "08:40→KRX 시가")):
    P("| %s | %+.2f | %+.2f | %.0f%% |" % (nm, mo[c].mean(), mn[c].mean(), (mo[c] < mn[c].mean()).mean() * 100))
P("\n새 날 하루씩: " + " · ".join("%s 당일 %+.1f 20일 %+.1f" % (d[4:], r.mday, r.m20) for d, r in mn.iterrows()))
P("\n## 옛 기간 — 장 상태별 규칙 성적 (건당 · 승률 · 건수) 와 새 날\n")
P("| 지표 | 나쁜 1/3 | 중간 | 좋은 1/3 | 새 날 실제 |"); P("|---|---|---|---|---|")
for c, nm in (("mday", "당일 등락"), ("m20", "직전 20일"), ("mpre", "장전 중앙"), ("mgap", "시가 갭"), ("m840", "08:40→시가")):
    q = mo[c].quantile([1 / 3, 2 / 3]).to_numpy(); cells = []
    for lo, hi in ((-1e9, q[0]), (q[0], q[1]), (q[1], 1e9)):
        z = old[(old[c] > lo) & (old[c] <= hi)]
        cells.append("%+.2f%% · %.0f%% · %d" % (z.r_vwhs.mean(), (z.r_vwhs > 0).mean() * 100, len(z)))
    nb = ["나쁜", "중간", "좋은"][int(np.searchsorted(q, mn[c].mean()))]
    P("| %s | %s | %s | %s | %+.2f%% (장 %s 쪽) |" % (nm, *cells, new.r_vwhs.mean(), nb))
P("\n## 장 상태로 맞춘 기대치 (옛 기간 회귀 → 새 날)\n")
X = ["mday", "m20", "mpre", "mgap", "m840"]
A = old.dropna(subset=X + ["r_vwhs"]); Bn = new.dropna(subset=X + ["r_vwhs"])
Xa = np.column_stack([np.ones(len(A))] + [A[c] for c in X]); b = np.linalg.lstsq(Xa, A.r_vwhs.to_numpy(), rcond=None)[0]
pred = np.column_stack([np.ones(len(Bn))] + [Bn[c] for c in X]) @ b
P("계수: " + " · ".join("%s %+.2f" % (n, v) for n, v in zip(["상수"] + X, b)))
P("새 날 %d건: 장 상태로 맞춘 기대 %+.2f%% · 실제 %+.2f%% · 장으로 설명 안 되는 몫 %+.2f%%p" % (len(Bn), pred.mean(), Bn.r_vwhs.mean(), Bn.r_vwhs.mean() - pred.mean()))
res = A.r_vwhs.to_numpy() - Xa @ b
rng = np.random.default_rng(3); bs = rng.choice(res, (100000, len(Bn))).mean(1)
P("옛 기간 잔차에서 %d건 뽑아 이만큼 나쁠 확률 %.3f%%" % (len(Bn), (bs <= Bn.r_vwhs.mean() - pred.mean()).mean() * 100))
P("\n## 옛 기간에서 새 날과 비슷한 장(당일 하락 & 직전 20일 하락)만\n")
z = old[(old.mday < 0) & (old.m20 < 0)]
P("%d건 · 건당 %+.2f%% · 승률 %.0f%%" % (len(z), z.r_vwhs.mean(), (z.r_vwhs > 0).mean() * 100))
z = old[(old.mday < -1)]
P("당일 장 -1%%↓ 날만: %d건 · 건당 %+.2f%% · 승률 %.0f%%" % (len(z), z.r_vwhs.mean(), (z.r_vwhs > 0).mean() * 100))
(ROOT / "reports" / "t5_mkt_1114.md").write_text("\n".join(OUT), encoding="utf-8")
