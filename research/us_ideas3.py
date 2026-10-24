# -*- coding: utf-8 -*-
"""미장 후보 3차 (2026-10-25) — C8 '갭 하락 & 첫 30분 반등 → 10:00 매수' 몰림·시장 효과 점검. H0367.
 · 날 바구니(신호 날마다 그날 신호 평균) — 하루 109건 몰린 날이 있어서 건당 평균이 몇 날에 끌려가는지
 · 하루 위 N개(첫 30분 반등 큰 순 · 갭 깊은 순)만
 · 지수로 직접: SPY·QQQ·IWM 갭 하락 & 첫 30분 반등 → 10:00→종가
    python research/us_ideas3.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
from verdict import log_trials

COST = 0.20
OUT = []; CELLS = [0]
def P(s=""): OUT.append(s); print(s, flush=True)
pct = lambda a, b: (a / b - 1) * 100


def st(x):
    x = pd.Series(x).dropna()
    if len(x) < 10: return None
    t = x.mean() / (x.std() / np.sqrt(len(x))) if x.std() > 0 else 0
    return dict(n=len(x), mean=x.mean(), med=x.median(), win=(x > 0).mean() * 100, t=t)


def cell(s, n=0):
    return "- (%d)" % n if not s else "%+.2f · 중앙 %+.2f · %.0f%% · t%.1f (%d)" % (s["mean"], s["med"], s["win"], s["t"], s["n"])


def row(name, D, col="rest", net=True, cut="20250101", basket=False):
    CELLS[0] += 1
    X = D.groupby("d")[col].mean().reset_index() if basket else D
    v = X[col] - (COST if net else 0)
    L, V = v[X.d < cut], v[X.d >= cut]
    P("| %s | %s | %s |" % (name + (" [날 바구니]" if basket else ""), cell(st(L), L.notna().sum()), cell(st(V), V.notna().sum())))


def head(t, note=""):
    P("\n### " + t)
    if note: P(note)
    P("\n| 칸 | 학습 2022~24 (평균 · 중앙 · 승률 · t · 건/날) | 검증 2025~ |"); P("|---|---|---|")


t0 = time.time()
A = pd.read_parquet(ROOT / "cache" / "m1_daysum_us.parquet").sort_values(["t", "d"]).reset_index(drop=True)
A = A[(A.nb >= 300) & (A.o > 0) & (A.pc > 0)].copy()
g = A.groupby("t", sort=False)
A["gap"] = pct(A.o, A.pc); A["r30"] = pct(A.p1000, A.o); A["rest"] = pct(A.c, A.p1000)
A["v20"] = g.val.transform(lambda s: s.shift(1).rolling(20, min_periods=10).mean())
A["vk"] = A.groupby("d").v20.rank(ascending=False)
A = A[A.d >= "20220101"]
spy = A[A.t == "SPY"].set_index("d")
A["sgap"] = A.d.map(spy.gap); A["sr30"] = A.d.map(spy.r30)
P("# 미장 후보 3차 — C8 반등 점검 · %s" % time.strftime("%Y-%m-%d"))

G = A[A.vk <= 500]
Z = G[(G.gap <= -4) & (G.r30 >= 3)]
head("① 날 바구니 — 신호 날마다 그날 신호 평균", "대형 500 · 갭 ≤ -4% & 첫 30분 +3%↑ · 10:00→종가")
row("전부", Z); row("전부", Z, basket=True)
Zm = Z[Z.sgap < -0.5]
row("SPY 갭 < -0.5", Zm); row("SPY 갭 < -0.5", Zm, basket=True)
row("SPY 갭 ≥ -0.5", Z[Z.sgap >= -0.5], basket=True)
P("\n날마다 건수 많은 날 위 8: " + " · ".join("%s %d건 %+.2f" % (d, len(q), (q.rest - COST).mean()) for d, q in sorted(Z.groupby("d"), key=lambda kv: -len(kv[1]))[:8]))
for N in (3, 5, 10):
    for nm, key in (("첫 30분 반등 큰 순", "r30"), ("갭 깊은 순", "gap")):
        Zt = Z.sort_values(key, ascending=(key == "gap")).groupby("d").head(N)
        row("하루 위 %d (%s)" % (N, nm), Zt, basket=True)

head("② 지수로 직접 — 갭 하락 & 첫 30분 반등 → 10:00→종가")
for tk in ("SPY", "QQQ", "IWM"):
    X = A[A.t == tk]
    for gth, rth in ((-0.5, 0.3), (-0.5, 0.5), (-1.0, 0.5), (-1.0, 1.0)):
        row("%s 갭 ≤ %.1f%% & 첫 30분 +%.1f%%↑" % (tk, gth, rth), X[(X.gap <= gth) & (X.r30 >= rth)])
    row("%s [대조] 갭 ≤ -0.5%% & 첫 30분 더 빠짐 (비용 전)" % tk, X[(X.gap <= -0.5) & (X.r30 < 0)], net=False)

head("③ 시장 갭 하락 & 시장 반등한 날의 대형주 바구니", "SPY 갭 ≤ -0.5% & SPY 첫 30분 +0.3%↑ 인 날, 대형 100 중 갭 ≤ -2% & 첫 30분 +1%↑ 종목")
D3 = A[(A.sgap <= -0.5) & (A.sr30 >= 0.3)]
B = D3[(D3.vk <= 100) & (D3.gap <= -2) & (D3.r30 >= 1)]
row("대형 100 갭 ≤ -2% & 반등 +1%↑", B, basket=True)
B = D3[(D3.vk <= 500) & (D3.gap <= -4) & (D3.r30 >= 3)]
row("대형 500 갭 ≤ -4% & 반등 +3%↑", B, basket=True)
P("\n칸 수 %d · %.1f분" % (CELLS[0], (time.time() - t0) / 60))
log_trials("us_ideas3_20261025", CELLS[0])
(ROOT / "reports" / "us_ideas3_20261025.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
