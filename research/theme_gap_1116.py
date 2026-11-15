# -*- coding: utf-8 -*-
"""같은 테마 안에서 장전 갭이 더 빠지거나 더 오른 종목 — 2026-11-16 사용자 "같은 테마 종목 중 장전 갭이 더 빠지거나 더 오른 건?".
자료: C:/temp/kp/openplay/days.parquet(openplay_1116 — 시가 갭·시가→10/30/60분·종가, 비용 0.28 뒤) × kospi.db sector(테마 252개·749종목, 업종 73개 — **2026-08-28 명단 한 장**을 과거에 씌움 → 편향 주의).
테마-날: 유니버스 안 구성 종목 4개↑. 테마 갭 = 구성 종목 갭 중앙. 상대 갭 = 종목 갭 − 테마 갭.
판: 테마가 뜬 날(테마 갭 ≥ +1.5·+3) / 빠진 날(≤ -1.5·-3) / 아무 날 × 테마 안에서 가장 덜 오른(더 빠진) 종목 · 가장 많이 오른(덜 빠진) 종목 · 상대 갭 문턱(±2·±4%p)
대조: 같은 날 시장 평균 · 같은 테마-날 나머지 구성 종목 평균. 학습 22-12~24 · 검증 25~.
    python research/theme_gap_1116.py
"""
import math, sqlite3, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
EX = ("x10", "x30", "x60", "xc"); PER = (("20221201", "20241231"), ("20250101", "20991231"))
OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))
A = pd.read_parquet(r"C:\temp\kp\openplay\days.parquet", columns=["t", "d", "gap", "a20"] + list(EX))
mk = A.groupby("d")[list(EX)].mean()
c = sqlite3.connect("file:" + str(BASE / "data" / "kospi.db") + "?mode=ro", uri=True)
S = pd.read_sql("select kind, gid, gname, ticker t from sector where snap='20260828'", c)
t_ = lambda s: s.mean() / s.std(ddof=1) * math.sqrt(len(s)) if len(s) > 2 and s.std(ddof=1) > 0 else 0


def study(kind, ko):
    G = S[S.kind == kind]
    G = G[G.groupby("gid").t.transform("size").between(4, 60)]                    # 너무 큰 묶음(지주사·밸류업 등)은 테마로 안 봄
    X = A.merge(G[["gid", "t"]], on="t")
    g = X.groupby(["d", "gid"])
    X["n"] = g.t.transform("size"); X = X[X.n >= 4]
    g = X.groupby(["d", "gid"])
    X["tg"] = g.gap.transform("median"); X["rel"] = X.gap - X.tg
    X["rk_lo"] = g.gap.rank(method="first"); X["rk_hi"] = g.gap.rank(method="first", ascending=False)
    for x in EX:
        s, n = g[x].transform("sum"), g[x].transform("count")
        X["p_" + x] = (s - X[x].fillna(0)) / (n - X[x].notna()).replace(0, np.nan)      # 같은 테마-날 나머지 평균
        X["m_" + x] = X.d.map(mk[x])
    P("\n## %s — 묶음 %d개 · 종목 %d · 테마-날 %d\n" % (ko, G.gid.nunique(), G.t.nunique(), X.groupby(["d", "gid"]).ngroups))
    P("| 날 | 고르는 종목 | 매도 | 학습 건·날 | 학습 건당 | 날 바구니(t) | 시장 대비 | 같은 테마 대비(t) | 검증 건·날 | 검증 건당 | 날 바구니(t) | 시장 대비 | 같은 테마 대비(t) |"); P("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    DAYS = (("테마 갭 +1.5%↑", lambda z: z.tg >= 1.5), ("테마 갭 +3%↑", lambda z: z.tg >= 3), ("테마 갭 -1.5%↓", lambda z: z.tg <= -1.5), ("테마 갭 -3%↓", lambda z: z.tg <= -3), ("아무 날", lambda z: z.tg > -99))
    PICK = (("가장 덜 오른(더 빠진) 1종목", lambda z: z.rk_lo == 1), ("가장 많이 오른(덜 빠진) 1종목", lambda z: z.rk_hi == 1),
            ("테마보다 2%p↓", lambda z: z.rel <= -2), ("테마보다 4%p↓", lambda z: z.rel <= -4), ("테마보다 2%p↑", lambda z: z.rel >= 2), ("테마보다 4%p↑", lambda z: z.rel >= 4))
    for dn, dm in DAYS:
        for pn, pm in PICK:
            Z = X[dm(X) & pm(X)].drop_duplicates(["t", "d"])
            for x in ("x30", "xc"):
                cells = []
                for a, b in PER:
                    z = Z[(Z.d >= a) & (Z.d <= b)].dropna(subset=[x])
                    if len(z) < 30: cells = None; break
                    d = z.groupby("d")[x].mean(); e = z.assign(e=z[x] - z["p_" + x]).groupby("d").e.mean().dropna()
                    cells.append("%d·%d | %+.2f%% | %+.2f%% (%.1f) | %+.2f | %+.2f (%.1f)" % (len(z), len(d), z[x].mean(), d.mean(), t_(d), (z[x] - z["m_" + x]).mean(), e.mean(), t_(e)))
                if cells: P("| %s | %s | %s | %s | %s |" % (dn, pn, x, cells[0], cells[1]))


study("theme", "테마(2026-08-28 명단)")
study("upjong", "업종(2026-08-28 명단, 73개)")
(ROOT / "theme_gap_1116.out").write_text("\n".join(OUT), encoding="utf-8")
