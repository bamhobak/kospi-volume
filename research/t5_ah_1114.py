# -*- coding: utf-8 -*-
"""2026-11-14 t5_why_1114 후속 — [장전 되돌림] '어제 통합 종가에 섞인 장후 움직임' 변형 실측.
새 날(10-09~11-12) 규칙 거래 62% 가 전날 장후 +1%↑(안정기 25%) — 장전 '하락'이 장후 상승을 도로 내준 것.
변형: ① 지금 판 ② 장후 +1%↑ 빼기(문턱 0.5·1·2) ③ 깊이를 KRX 종가 기준으로(rpreK = 장전÷어제 KRX 종가 − 그날 중앙)
      ④ 두 기준 다 -3%p↓ — 순위·붐비는 날은 그 판 신호로 다시 셈. 어제 KRX 종가·장후 움직임은 08:40 에 아는 값.
    python research/t5_ah_1114.py"""
import sys, glob
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent; C = ROOT / "cache"
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd, math
OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))
CUM = 1_019_060_000
S = pd.read_pickle(r"C:\temp\kp\t5_full_panel_1114.pkl")
K = pd.read_parquet(C / "m1_daysum.parquet", columns=["t", "d", "c"]); K["t"] = K.t.astype(str); K["d"] = K.d.astype(str); K = K[K.d >= "20250101"]; ks = []
for f in sorted(glob.glob(str(BASE / "data/m1/KR/day/*.parquet"))):
    d = Path(f).stem
    if d <= K.d.max(): continue
    x = pd.read_parquet(f, columns=["t", "ts", "c", "v"]); x = x[x.v > 0].sort_values("ts")
    g = x.groupby("t").agg(c=("c", "last")).reset_index(); g["d"] = d; ks.append(g)
K = pd.concat([K] + ks, ignore_index=True).sort_values(["t", "d"]); K["kpc"] = K.groupby("t").c.shift(1)
S = S.merge(K[["t", "d", "kpc"]], on=["t", "d"], how="left")
S["ah"] = (S.tc_y / S.kpc - 1) * 100
S["preK"] = (S.pT / S.kpc - 1) * 100
S.loc[S.preK.abs() >= 30, "preK"] = np.nan
S["rpreK"] = S.preK - S.groupby("d").preK.transform("median")


def pick(sig, rkcol):
    Z = S[sig].copy()
    Z["rk2"] = S[sig.index.isin(Z.index) | True].loc[Z.index, rkcol]
    return Z


def rule(depth, ahmax=None, both=False):
    s = S.copy()
    key = "rpre" if depth == "rpre" else "rpreK"
    m = (s[key] <= -3) & (s.cum <= CUM)
    if both: m &= (s.rpre <= -3) & (s.rpreK <= -3)
    if ahmax is not None: m &= s.ah.fillna(0) <= ahmax
    s["rk2"] = s.groupby("d")[key].rank(method="first")         # 순위는 그 판 깊이로(두꺼운 종목도 셈 — 지금 판과 같게)
    sig = s[m]
    ns = sig.groupby("d").size()
    Z = sig[sig.rk2 <= 4].copy(); Z["ns"] = Z.d.map(ns)
    return Z[(Z.ns < 10) & Z.r_vwhs.notna()]


def stt(Z):
    if not len(Z): return "-"
    d = Z.groupby("d").r_vwhs.mean(); sd = d.std(ddof=1)
    t = d.mean() / sd * math.sqrt(len(d)) if len(d) > 1 and sd > 0 else 0
    return "%+.2f%% · 승 %.0f%% · %d건 (t %.1f)" % (Z.r_vwhs.mean(), (Z.r_vwhs > 0).mean() * 100, len(Z), t)


PER = (("2025-07~12", "20250701", "20251231"), ("2026-01~06", "20260101", "20260630"), ("2026-07~10-08", "20260701", "20261008"),
       ("**새 날 10-09~11-12**", "20261009", "20261112"), ("전체 2025-03~", "20250301", "20261112"))
V = (("① 지금 판(통합 종가 기준)", dict(depth="rpre")), ("② 장후 +2%↑ 빼기", dict(depth="rpre", ahmax=2)), ("② 장후 +1%↑ 빼기", dict(depth="rpre", ahmax=1)),
     ("② 장후 +0.5%↑ 빼기", dict(depth="rpre", ahmax=0.5)), ("③ 깊이를 KRX 종가 기준으로", dict(depth="rpreK")), ("④ 두 기준 다 -3%p↓", dict(depth="rpre", both=True)))
P("# [장전 되돌림] 장후 움직임 변형 (11-14)\n")
P("| 변형 | " + " | ".join(p[0] for p in PER) + " |"); P("|---" * (len(PER) + 1) + "|")
RES = {}
for nm, kw in V:
    Z = rule(**kw); RES[nm] = Z
    P("| %s | " % nm + " | ".join(stt(Z[(Z.d >= a) & (Z.d <= b)]) for _, a, b in PER) + " |")
P("\n하루 평균 건수(전체 기간 거래일 %d일): " % S.d.nunique() + " · ".join("%s %.2f" % (nm[:2], len(Z) / S.d.nunique()) for nm, Z in RES.items()))
P("\n장후 움직임 구간별 — 지금 판 신호(전체 기간)\n")
Z = RES["① 지금 판(통합 종가 기준)"]
P("| 장후 | 안정기(2025-07~10-08) | 새 날 |"); P("|---|---|---|")
for nm, lo, hi in (("-1%↓", -99, -1), ("-1~0", -1, 0), ("0~+0.5", 0, .5), ("+0.5~1", .5, 1), ("+1~2", 1, 2), ("+2~4", 2, 4), ("+4%↑", 4, 99)):
    z = Z[(Z.ah > lo) & (Z.ah <= hi)]
    P("| %s | %s | %s |" % (nm, stt(z[(z.d >= "20250701") & (z.d <= "20261008")]), stt(z[z.d >= "20261009"])))
P("\n장후 +1%%↑ 비중 달별(지금 판 신호): " + " · ".join("%s %.0f%%(%d)" % (m[2:], (g.ah > 1).mean() * 100, len(g)) for m, g in Z.groupby(Z.d.str[:6])))
A = S[S.d >= "20250501"]
P("\n전 종목 장후 움직임 크기(|장후| 평균, 달별): " + " · ".join("%s %.2f" % (m[2:], g.ah.abs().mean()) for m, g in A.groupby(A.d.str[:6])))
(ROOT / "reports" / "t5_ah_1114.md").write_text("\n".join(OUT), encoding="utf-8")
