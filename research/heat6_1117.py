# -*- coding: utf-8 -*-
"""H0425 체결 가능 — 단일가 날 마지막(종가) 단일가에 실제 얼마가 체결되나 (2026-11-17 사용자 "금액 상관없이 원하는 가격에 가능한 거야?").
1분봉(거래 있는 분만)에서 D+1(사는 날)·D+3(파는 날)의 15:20 뒤 마지막 봉 체결 금액 → 내 주문이 그 한 번의 몇 %인가."""
import os, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parent.parent
OUT = []; P_ = lambda s="": (OUT.append(s), print(s, flush=True))
X = pd.read_pickle("C:/temp/kp/heat_ev4.pkl").dropna(subset=["a1e"]); X = X[X.day >= "20230101"]
P = pd.read_pickle(BASE / "research" / "cache" / "factory_px.pkl"); cal = sorted(P[P.date >= "20151001"].date.unique()); del P
rows = []
for t, g in X.groupby("t"):
    f = BASE / "data" / "m1" / "KR" / "bf" / ("%s.parquet" % t)
    if not f.exists(): continue
    B = pd.read_parquet(f, columns=["ts", "c", "v"]); B = B[B.v > 0]
    k = pd.to_datetime(B.ts.values + 9 * 3600, unit="s"); B["d"] = k.strftime("%Y%m%d"); B["hm"] = k.strftime("%H%M")
    for _, r in g.iterrows():
        for kk, nm in ((1, "사는 날(D+1)"), (3, "파는 날(D+3)")):
            z = B[B.d == cal[r.i + kk]]; n = z.hm.nunique()
            if n < 5 or n > 20: continue
            last = z[z.hm >= "1520"]; prev = z[z.hm < "1520"]
            rows.append(dict(side=nm, a1e=r.a1e, last=(last.c * last.v).sum() / 1e4, n=n, lhm=last.hm.max() if len(last) else "",
                             mv=abs(last.c.iloc[-1] / prev.c.iloc[-1] - 1) * 100 if len(last) and len(prev) else np.nan))
R = pd.DataFrame(rows)
P_("# H0425 체결 가능 — 마지막 단일가(종가) 한 번에 체결되는 금액 (검증 2023~, 1분봉 있는 %d건)\n" % len(R))
P_("마지막 체결 시각: %s · 하루 단일가 횟수 중앙 %d\n" % (R.lhm.value_counts().head(3).to_dict(), R.n.median()))
P_("| 대상 | 날 | 건 | 종가 단일가 체결액 중앙(만) | 아래 25% | 아래 10% | 체결 없음 | 200만이 차지 | 500만 | 1,000만 | 직전 단일가→종가 움직임 중앙 |\n|---|---|---|---|---|---|---|---|---|---|---|")
for nm, m in (("전체", R.a1e > 0), ("거래대금 60억↑", R.a1e >= 60), ("50억↑", R.a1e >= 50), ("40억↑", R.a1e >= 40), ("30억↑", R.a1e >= 30), ("30억↓", R.a1e < 30)):
    for sd in ("사는 날(D+1)", "파는 날(D+3)"):
        z = R[m & (R.side == sd)]; v = z["last"]
        P_("| %s | %s | %d | %.0f | %.0f | %.0f | %.0f%% | %.1f%% | %.1f%% | %.1f%% | %.2f%% |" % (nm, sd, len(z), v.median(), v.quantile(.25), v.quantile(.1), (v <= 0).mean() * 100, 200 / v.median() * 100, 500 / v.median() * 100, 1000 / v.median() * 100, z.mv.median()))
(BASE / "research" / "reports" / "heat6_1117.md").write_text("\n".join(OUT), encoding="utf-8")
