# -*- coding: utf-8 -*-
"""T3 후보 [미장 따라 밀린 갭 하락] = T1 & 그 종목 짝 미장으로 본 예상 갭(tr_pred) ≤ -0.5 — 갭별·문턱 조정·T2 겹침.
(2026-10-11 사용자: "갭별로 그리고 다른 수치들 조정해서 조사해 보고, T1이랑은 교집합인지, T2와의 겹침도")
  ① 공장 패널(2016~, 시가→종가 일봉, 비용 0.23%) — 갭 크기별 · 문턱 조정(미장 예상 갭·시장 대비·거래량·유동성·갭 분위·주가)
  ② T2 겹침 — research/cache/t1_prevday.pkl(T1 후보 1,991건 22.12~26.08, 전날 14:00→종가 y_lasth · 1분봉 시가→종가 ret)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "factory"))
import numpy as np, pandas as pd
import lab, feats as FT

U = lab.hist().copy()
U["ret"] = U.oc.astype(float).clip(-60, 60) - FT.COST
ok = U.oc.notna() & U.tr_pred.notna()
TR, VA = lab.TR, lab.VA
T1 = U.t1 & ok
P5 = U.tr_pred <= -0.5
T3 = T1 & P5


def st(m, a, b):
    return lab.stats(U.loc[m & (U.date >= a) & (U.date <= b), ["date", "ret", "t1"]])


def row(name, m):
    s_t, s_v = st(m, *TR), st(m, *VA)
    f = lambda s: ("%4d %+6.2f %4.1f%% t%4.1f %d/%d" % (s["n"], s["mean"], s["win"], s["t"], s["ypos"], s["ny"])) if s else "     -"
    ov = (m & U.t1).sum() / max(m.sum(), 1) * 100
    print("%-46s | 학습 %s | 검증 %s | T1안 %3.0f%%" % (name[:46], f(s_t), f(s_v), ov))


print("건수 평균 승률 하루t 플러스해 · 'T1안' = 그 판의 거래 중 T1 에도 드는 비율(100% = 완전히 T1 의 부분집합)")
row("T1", T1); row("T3 = T1 & 짝 미장 예상 갭 ≤ -0.5", T3); row("T1 중 T3 아닌 것", T1 & ~P5)

print("\n== ① 실제 갭 크기별 (T3 / 대조: T1 중 T3 아닌 것)")
for lo, hi in ((-3, -2), (-5, -3), (-10, -5), (-99, -10)):
    b = (U.gap > lo) & (U.gap <= hi)
    row("T3 & 갭 %+d ~ %+d%%" % (lo, hi), T3 & b)
    row("   대조 T1-T3 & 갭 %+d ~ %+d%%" % (lo, hi), T1 & ~P5 & b)

print("\n== ② 짝 미장 예상 갭 문턱")
for th in (0, -0.3, -0.5, -0.8, -1, -1.5):
    row("T1 & 미장 예상 갭 ≤ %+.1f" % th, T1 & (U.tr_pred <= th))

print("\n== ③ T3 안에서 문턱 조이기 / T1 밖으로 풀기")
row("T3 & 시장 대비 -3%p↓", T3 & (U.rgap <= -3))
row("T3 & 시장 대비 -4%p↓", T3 & (U.rgap <= -4))
row("T3 & 거래량배수 하위 20%", T3 & (U.q_vm <= 0.2))
row("T3 & 거래량배수 하위 10%", T3 & (U.q_vm <= 0.1))
row("T3 & 유동성 아래 1/5", T3 & (U.liq <= 0.2))
row("T3 & 갭 하위 5%", T3 & (U.q_gap <= 0.05))
row("T3 & 어제 종가 5천원↓", T3 & (U.px < 5000))
row("T3 & 5일선 아래", T3 & (U.d5 < 0))
c = lambda gq=.1, vq=.3, lq=1 / 3, rg=-2.0: ok & P5 & (U.q_gap <= gq) & (U.q_vm <= vq) & (U.liq <= lq) & (U.rgap <= rg)
row("[풀기] 시장 대비 -1.5%p", c(rg=-1.5))
row("[풀기] 거래량배수 하위 50%", c(vq=.5))
row("[풀기] 유동성 아래 1/2", c(lq=.5))
row("[풀기] 갭 하위 20%", c(gq=.2))

print("\n== ④ T2 겹침 (22.12~26.08 T1 후보, 1분봉 시가→종가 · 비용 0.23%)")
P = pd.read_pickle(Path(__file__).resolve().parent / "cache" / "t1_prevday.pkl")
P = P[P.ok.astype(bool)].copy() if "ok" in P.columns else P.copy()
P = P.merge(U[["ticker", "date", "tr_pred"]], on=["ticker", "date"], how="left")
P["t2"] = P.y_lasth <= -1
P["t3"] = P.tr_pred <= -0.5
print("  T1 후보 %d건 중 미장 예상 갭 있는 것 %d건" % (len(P), P.tr_pred.notna().sum()))
P = P[P.tr_pred.notna() & P.y_lasth.notna()]
def g(name, m):
    x = P.loc[m, "ret"]
    va = P.loc[m & (P.date >= "20250101"), "ret"]
    print("  %-26s %4d건 평균 %+5.2f%% 승률 %4.1f%%  | 그중 2025~ %3d건 %+5.2f%% %4.1f%%" % (
        name, len(x), x.mean(), (x > 0).mean() * 100, len(va), va.mean() if len(va) else np.nan, (va > 0).mean() * 100 if len(va) else np.nan))
g("T1 전체", P.ret.notna())
g("T2 (전날 막판 -1%↓)", P.t2)
g("T3 (짝 미장 -0.5↓)", P.t3)
g("T2 이면서 T3", P.t2 & P.t3)
g("T2 만 (T3 아님)", P.t2 & ~P.t3)
g("T3 만 (T2 아님)", P.t3 & ~P.t2)
g("둘 다 아님", ~P.t2 & ~P.t3)
n2, n3, nb = P.t2.sum(), P.t3.sum(), (P.t2 & P.t3).sum()
print("  겹침: T3 중 T2 인 것 %d/%d (%.0f%%) · T2 중 T3 인 것 %d/%d (%.0f%%)" % (nb, n3, nb / max(n3, 1) * 100, nb, n2, nb / max(n2, 1) * 100))
