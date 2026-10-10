# -*- coding: utf-8 -*-
"""T1 파생 2 — '밤사이 미장이 빠진 날의 갭 하락주'(t1_derive.py 에서 가장 뚜렷했던 각도) 파기.
  ① 미장 예상 갭(tr_pred) 문턱 · ② 그런 날 T1 조건 풀기(유동성·거래량·시장 대비) · ③ 해마다 · ④ T2·기존 T1 과 겹침
잣대 = 공장(lab): 시가→종가 비용 0.23%, 학습 2016~22 · 검증 2023~ (tr_pred 는 2014~).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "factory"))
import numpy as np, pandas as pd
import lab, feats as FT

U = lab.hist()
U["ret"] = U.oc.astype(float).clip(-60, 60) - FT.COST
ok = U.oc.notna() & U.tr_pred.notna()
TR, VA = lab.TR, lab.VA
base = U.t1 & ok


def st(m, a, b):
    return lab.stats(U.loc[m & (U.date >= a) & (U.date <= b), ["date", "ret", "t1"]])


def row(name, m):
    s_t, s_v = st(m, *TR), st(m, *VA)
    f = lambda s: ("%5d %+6.2f %4.1f%% t%4.1f %d/%d 하루%4.1f" % (s["n"], s["mean"], s["win"], s["t"], s["ypos"], s["ny"], s["perday"])) if s else "      -"
    ov = (m & U.t1).sum() / max(m.sum(), 1) * 100
    print("%-50s | 학습 %s | 검증 %s | T1겹침 %3.0f%%" % (name[:50], f(s_t), f(s_v), ov))


print("== ① 미장 예상 갭 문턱 (T1 안에서)")
row("T1 전체(2014~)", base)
for th in (0.5, 0, -0.5, -1, -1.5, -2):
    row("T1 & 미장 예상 갭 ≤ %+.1f" % th, base & (U.tr_pred <= th))

d1 = U.tr_pred <= -1
print("\n== ② 미장 예상 갭 ≤ -1 인 날 — T1 조건 풀기")
row("갭↓10% · 거래량↓30% · 유동성↓1/3 · 시장대비 -2%p (=T1)", ok & d1 & U.t1)
row("유동성 조건 뺌", ok & d1 & (U.q_gap <= .1) & (U.q_vm <= .3) & (U.rgap <= -2))
row("거래량 조건 뺌", ok & d1 & (U.q_gap <= .1) & (U.liq <= 1 / 3) & (U.rgap <= -2))
row("시장 대비 조건 뺌", ok & d1 & (U.q_gap <= .1) & (U.q_vm <= .3) & (U.liq <= 1 / 3))
row("갭↓10% 만", ok & d1 & (U.q_gap <= .1))
row("갭↓10% · 유동성↓1/3", ok & d1 & (U.q_gap <= .1) & (U.liq <= 1 / 3))
row("갭↓20% · 거래량↓30% · 유동성↓1/3 · 시장대비 -2%p", ok & d1 & (U.q_gap <= .2) & (U.q_vm <= .3) & (U.liq <= 1 / 3) & (U.rgap <= -2))
row("시장대비 -3%p 로 세게", ok & d1 & U.t1 & (U.rgap <= -3))
row("미장 예상 갭 ≤ -1 이 아닌 날의 T1(대조)", ok & ~d1 & U.t1)

print("\n== ③ 해마다 — T1 & 미장 예상 갭 ≤ -1")
m = ok & d1 & U.t1
T = U.loc[m, ["date", "ret"]]
for k, grp in T.groupby(T.date.str[:4]):
    nd = grp.date.nunique()
    print("  %s  %3d건 %3d일  평균 %+5.2f%%  승률 %4.1f%%" % (k, len(grp), nd, grp.ret.mean(), (grp.ret > 0).mean() * 100))
nd_all = U.loc[ok & d1, "date"].nunique(); nd_tot = U.loc[ok, "date"].nunique()
print("  미장 예상 갭 ≤ -1 인 날: %d일 / 전체 %d일 (%.0f%%)" % (nd_all, nd_tot, nd_all / nd_tot * 100))
print("  그런 날 하루 평균 후보 %.1f종목" % (T.groupby("date").size().mean()))
