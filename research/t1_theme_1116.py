# -*- coding: utf-8 -*-
"""[갭하락] 깊이를 '시장 대비' 대신·함께 '같은 테마(업종) 대비'로 — 2026-11-16 사용자 "응 한번 재봐".
자료: data/y1_hist.pkl(유니버스 일봉 재료 2015~2026-11-04: gap·rgap(시장 대비 갭)·liq·q_gap·q_vm·oc) × kospi.db sector 2026-08-28 테마(4~60종목 묶음)·업종 73개.
  ⚠ 명단 한 장을 과거에 씌움. trel = 종목 갭 − 같은 묶음(유니버스 안 3종목↑) 갭 중앙 · 묶음 여럿이면 평균.
지금 연구 정의 T1 = 크기 아래 2/3 · 갭 하위 40% · 어제 거래량 하위 30% · 시장 대비 ≤ -1.5 → 시가→종가 − 0.23.
    python research/t1_theme_1116.py
"""
import math, sqlite3, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))
U = pd.read_pickle(BASE / "data" / "y1_hist.pkl")
U = U[U.date >= "20160101"].dropna(subset=["oc", "gap"]).copy(); U["ret"] = U.oc - 0.23
c = sqlite3.connect("file:" + str(BASE / "data" / "kospi.db") + "?mode=ro", uri=True)
S = pd.read_sql("select kind, gid, ticker from sector where snap='20260828'", c)
S = S[S.groupby(["kind", "gid"]).ticker.transform("size").between(4, 60)]
S["g"] = S.kind + S.gid.astype(str)
X = U[["ticker", "date", "gap"]].merge(S[["g", "ticker"]], on="ticker")
gg = X.groupby(["date", "g"]).gap
X["n"] = gg.transform("size"); X["tg"] = gg.transform("median")
X = X[X.n >= 3]; X["trel"] = X.gap - X.tg
T = X.groupby(["ticker", "date"]).agg(trel=("trel", "mean"), tg=("tg", "mean")).reset_index()
U = U.merge(T, on=["ticker", "date"], how="left")
base = (U.liq <= 2 / 3) & (U.q_vm.fillna(1) <= 0.30)
T1 = U[base & (U.q_gap <= 0.40) & (U.rgap <= -1.5)]
PER = (("학습 16~22", "20160101", "20221231"), ("검증 23~", "20230101", "20991231"))
t_ = lambda s: s.mean() / s.std(ddof=1) * math.sqrt(len(s)) if len(s) > 2 and s.std(ddof=1) > 0 else 0


def line(nm, Z):
    cells = []
    for _, a, b in PER:
        z = Z[(Z.date >= a) & (Z.date <= b)]
        if len(z) < 30: cells.append("- | - | -"); continue
        d = z.groupby("date").ret.mean(); nd = U[(U.date >= a) & (U.date <= b)].date.nunique()
        cells.append("%d (하루 %.1f) | %+.2f%% · 승 %.0f%% | %+.2f%% (t %.1f) · 합 %+.0f" % (len(z), len(z) / nd, z.ret.mean(), (z.ret > 0).mean() * 100, d.mean(), t_(d), z.ret.sum()))
    P("| %s | %s | %s |" % (nm, cells[0], cells[1]))


H = "| 판 | 학습 건수 | 학습 건당 | 학습 날 바구니 · 수익 합(%p) | 검증 건수 | 검증 건당 | 검증 날 바구니 · 수익 합 |\n|---|---|---|---|---|---|---|"
P("유니버스 %d 종목-일 · 테마·업종 붙은 비율 %.0f%% · 지금 T1 %d건 중 붙은 것 %.0f%%\n" % (len(U), U.trel.notna().mean() * 100, len(T1), T1.trel.notna().mean() * 100))
P("### 1. 지금 [갭하락] 거래를 '같은 테마 대비 깊이'로 나누면\n"); P(H)
line("지금 T1 전부", T1); line("테마 없는 종목", T1[T1.trel.isna()]); K = T1[T1.trel.notna()]; line("테마 있는 종목 전부", K)
line("　테마보다 3%p↓ 더 빠짐", K[K.trel <= -3]); line("　테마보다 1.5~3%p 더 빠짐", K[(K.trel > -3) & (K.trel <= -1.5)]); line("　테마와 비슷(-1.5~0)", K[(K.trel > -1.5) & (K.trel <= 0)])
line("　테마보다 덜 빠짐(0↑ — 테마째 빠진 날)", K[K.trel > 0])
line("　테마 자체가 -1.5%↓ 빠진 날", K[K.tg <= -1.5]); line("　테마는 멀쩡(-0.5↑)한데 혼자 빠짐", K[K.tg > -0.5])
P("\n### 2. 규칙을 바꾸면 (크기·어제 거래량 조건은 그대로)\n"); P(H)
line("지금: 시장 대비 ≤ -1.5 (갭 하위 40%)", T1)
B = U[base & U.trel.notna()]
line("테마 있는 종목만 · 시장 대비 ≤ -1.5", T1[T1.trel.notna()])
for x in (-1.5, -2, -3): line("대신: 테마 대비 ≤ %.1f (시장 조건 없음)" % x, B[B.trel <= x])
for x in (-1, -1.5, -2): line("둘 다: 시장 대비 ≤ -1.5 & 테마 대비 ≤ %.1f" % x, T1[T1.trel <= x])
line("둘 중 하나: 시장 ≤ -1.5 또는 테마 ≤ -2 (갭 < 0)", U[base & (U.gap < 0) & (((U.q_gap <= 0.40) & (U.rgap <= -1.5)) | (U.trel <= -2))])
line("지금 T1 에서 '테마보다 덜 빠짐(0↑)'만 빼기", T1[~(T1.trel > 0)])
(ROOT / "t1_theme_1116.out").write_text("\n".join(OUT), encoding="utf-8")
