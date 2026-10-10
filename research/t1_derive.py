# -*- coding: utf-8 -*-
"""[갭 하락 조용주](T1) 파생 — 아직 안 판 각도로 (2026-10-11 사용자: "갭 하락 조용주 파생해서 다른 방식으로 파볼 수 있을까").

이미 한 것(H0285·0287·0291·0292·0295·0297)은 빼고:
  A 갭 원인 — 미장으로 설명되는 하락(tr_res≈0) vs 설명 안 되는 하락(tr_res 크게 음수)
  B 변동성 대비 갭 — gap ÷ vol20 (평소 출렁임 대비 얼마나 크게 빠졌나) · T1 의 갭 조건을 이걸로 바꾼 판
  C 며칠 모양 — 어제도 갭 하락 / 어제 갭 상승 뒤 오늘 하락 / 이틀 연속 T1
  D 수급 — 어제 외국인·기관 순매수 방향
  E 테마 열기(th) · 주가대(호가 단위)
  F NXT 개장(2025-03) 뒤 — 해마다·분기마다 살아 있나
잣대 = 공장(lab): 시가→종가, 비용 0.23%, 학습 2016~22 · 검증 2023~ · 참고 2005~15. 학습으로 고르고 검증은 확인.
    python research/t1_derive.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "factory"))
import numpy as np, pandas as pd
import lab, feats as FT

U = lab.hist()
U = U.sort_values(["ticker", "date"]).reset_index(drop=True)
g = U.groupby("ticker", sort=False)
U["gap_y"] = g.gap.shift(1)                                     # 어제 갭
U["t1_y"] = g.t1.shift(1).fillna(False).astype(bool)            # 어제도 T1
U["gapz"] = U.gap / U.vol20.replace(0, np.nan)                  # 변동성 대비 갭
U["ret"] = U.oc.astype(float).clip(-60, 60) - FT.COST
ok = U.oc.notna()
REF, TR, VA = lab.REF, lab.TR, lab.VA
base = U.t1 & ok


def st(m, a, b):
    T = U.loc[m & (U.date >= a) & (U.date <= b), ["date", "ret", "t1"]]
    return lab.stats(T)


def row(name, m, show_ref=True):
    s_r, s_t, s_v = st(m, *REF), st(m, *TR), st(m, *VA)
    f = lambda s: ("%5d %+6.2f %4.1f%% t%4.1f %d/%d" % (s["n"], s["mean"], s["win"], s["t"], s["ypos"], s["ny"])) if s else "      -"
    print("%-46s | 학습 %s | 검증 %s%s" % (name[:46], f(s_t), f(s_v), (" | 참고 " + f(s_r)) if show_ref else ""))
    return s_t, s_v


print("== 기준 T1(갭 하위10%·거래량배수 하위30%·유동성 아래 1/3·시장 대비 -2%p↓) — 건수 평균 승률 하루t 플러스해")
B_T, B_V = row("T1 기준", base)

print("\n== A 갭 원인: 실제 갭 - 미장으로 본 예상 갭(tr_res, 2014~)")
for lo, hi, nm in ((-99, -4, "tr_res ≤ -4 (미장으로 설명 안 됨, 크게)"), (-4, -2, "-4 < tr_res ≤ -2"),
                   (-2, -0.5, "-2 < tr_res ≤ -0.5"), (-0.5, 99, "tr_res > -0.5 (미장만큼 빠진 것)")):
    row("T1 & " + nm, base & (U.tr_res > lo) & (U.tr_res <= hi), show_ref=False)
row("T1 & 미장 예상 갭 ≥ 0 (밤사이 미장은 좋았는데 빠짐)", base & (U.tr_pred >= 0), show_ref=False)
row("T1 & 미장 예상 갭 ≤ -1 (미장 따라 빠짐)", base & (U.tr_pred <= -1), show_ref=False)

print("\n== B 변동성 대비 갭(gap ÷ 20일 변동성)")
for lo, hi in ((-99, -2.0), (-2.0, -1.2), (-1.2, -0.7), (-0.7, 99)):
    row("T1 & %s < gapz ≤ %s" % (lo, hi), base & (U.gapz > lo) & (U.gapz <= hi))
alt = ok & (U.gapz <= -1.2) & (U.q_vm <= 0.30) & (U.liq <= 1 / 3) & (U.rgap <= -2.0)
row("[대안] 갭조건을 gapz ≤ -1.2 로 바꾼 T1", alt)
row("[대안] gapz ≤ -1.2 이고 T1 아님(새로 잡히는 것만)", alt & ~U.t1)

print("\n== C 며칠 모양")
row("T1 & 어제도 갭 -2% 이하", base & (U.gap_y <= -2))
row("T1 & 어제 갭 +2% 이상(어제 갭상승 → 오늘 갭하락)", base & (U.gap_y >= 2))
row("T1 & 어제 갭 -2~+2", base & (U.gap_y > -2) & (U.gap_y < 2))
row("T1 & 어제도 T1(이틀 연속)", base & U.t1_y)

print("\n== D 수급(어제 외국인 fr · 기관 inst 순매수 비율, 2018~ 일부)")
for f, nm in (("fr", "외국인"), ("inst", "기관")):
    if f not in U.columns: continue
    q = U["q_" + f] if ("q_" + f) in U.columns else None
    if q is None: continue
    row("T1 & 어제 %s 순매수 상위 30%%" % nm, base & (q >= 0.7), show_ref=False)
    row("T1 & 어제 %s 순매도 하위 30%%" % nm, base & (q <= 0.3), show_ref=False)

print("\n== E 테마 열기(th) · 주가대")
if "q_th" in U.columns:
    row("T1 & 테마 열기 상위 30%", base & (U.q_th >= 0.7), show_ref=False)
    row("T1 & 테마 열기 하위 30%", base & (U.q_th <= 0.3), show_ref=False)
for lo, hi in ((0, 2000), (2000, 5000), (5000, 20000), (20000, 10 ** 9)):
    row("T1 & 어제 종가 %d~%d원" % (lo, hi), base & (U.px >= lo) & (U.px < hi))

print("\n== F 해마다·분기(검증 구간) — NXT 개장(2025-03-04) 전후")
T = U.loc[base & (U.date >= "20230101"), ["date", "ret"]]
for k, grp in T.groupby(T.date.str[:4]):
    print("  %s  %4d건  평균 %+5.2f%%  승률 %4.1f%%" % (k, len(grp), grp.ret.mean(), (grp.ret > 0).mean() * 100))
T["qq"] = T.date.str[:4] + "Q" + ((T.date.str[4:6].astype(int) - 1) // 3 + 1).astype(str)
for k, grp in T.groupby("qq"):
    if k >= "2024Q3":
        print("  %s  %4d건  평균 %+5.2f%%  승률 %4.1f%%" % (k, len(grp), grp.ret.mean(), (grp.ret > 0).mean() * 100))
