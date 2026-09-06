# -*- coding: utf-8 -*-
"""[조용한 신고가] 를 뺄까 — 2022년 이후 계좌로 답한다.

단독 표(solo_cum.py)에서 이 규칙은 2022~26 에 2024년 한 해 빼곤 번 게 없다. 그런데 9규칙 계좌에서는
가장 큰 자리(12%×7)를 쥐고 있어, 빼면 그 돈이 노는지 다른 규칙이 쓰는지에 따라 답이 갈린다.
  A) 현행
  B) 그냥 제거 — 자리가 빈 채로 논다
  C) 제거 + 나머지 여덟 규칙 비중 ×1.5 — 빈 돈을 다른 규칙이 쓴다(자리 수 mx 는 그대로)
  D) 제거 + 나머지 비중 ×2.0
구간: 2022~26 · 2024~26 · 2018~26. 같은 시드로 짝 비교.
사용: IX_FROM=2004-06-01 DART_FROM=20040101 PANEL_KP=panel_kp.pkl PANEL_KQ=panel_kq.pkl python p1_drop.py
"""
import io, os, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent; SEEDS = 12
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES = ns["KP"], ns["KQ"], ns["RULES"]
adates = sorted(set(KP.date) | set(KQ.date)); ADI = {d: i for i, d in enumerate(adates)}
rel = (BASE/"rules_relation.py").read_text(encoding="utf-8")
exec(rel[rel.index("def build(R):"):rel.index("S = build(RULES)")], globals())
exec(rel[rel.index("def sim(S, ds, seed):"):rel.index("ds = [d for d in adates")].replace(
     "return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid)",
     "return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid, curve=Cv)"), globals())
def variant(drop=None, scale=1.0):
    R = {}
    for rid, (P,h,st,pct,mx,c) in RULES.items():
        if rid == drop: continue
        R[rid] = (P,h,st,min(pct*scale, 100.0/mx),mx,c)
    return build(R)
# 교락 제거: '뺀 효과' 와 '키운 효과' 를 가르려면 같은 배율에서 두고/빼고를 짝지어야 한다
def variant2(drop, scale):
    R = {}
    for rid, (P,h,st,pct,mx,c) in RULES.items():
        if rid == drop: continue
        sc = 1.0 if rid == "P1" else scale          # 조용한 신고가는 비중 그대로, 나머지만 키움
        R[rid] = (P,h,st,min(pct*sc, 100.0/mx),mx,c)
    return build(R)
VAR = [("A 현행", variant()),
       ("E 두고 ×1.5", variant2(None, 1.5)), ("C 빼고 ×1.5", variant2("P1", 1.5)),
       ("F 두고 ×2.0", variant2(None, 2.0)), ("D 빼고 ×2.0", variant2("P1", 2.0))]
PER = [("2022~26","20220101","20991231"), ("2018~26","20180101","20991231")]
print(f"  {'안':<16}" + "".join(f"{p[0]:>26}" for p in PER))
print(f"  {'':<16}" + "".join(f"{'자산':>10}{'낙폭':>8}{'시드승':>8}" for p in PER))
print("  " + "-"*96)
BASE_N = {}; CURVES = {}
for nm, S in VAR:
    row = ""
    for pn, lo, hi in PER:
        ds = [d for d in adates if lo <= d <= hi]
        R = [sim(S, ds, k) for k in range(SEEDS)]
        nav = [r["nav"] for r in R]; mdd = np.median([r["mdd"] for r in R])
        if nm.startswith("A"): BASE_N[pn] = nav; w = "기준"
        else: w = f"{sum(a>b for a,b in zip(nav, BASE_N[pn]))}/{SEEDS}"
        row += f"{np.median(nav):>9.2f}배{mdd:>7.0f}%{w:>8}"
        if pn == "2022~26": CURVES[nm] = (ds, R)
    print(f"  {nm:<16}{row}")
print("\n  연도별 계좌 수익률 (2022~26 · 중앙값)")
print(f"  {'해':<6}" + "".join(f"{nm:>16}" for nm, _ in VAR))
for y in ("2022","2023","2024","2025","2026"):
    row = f"  {y:<6}"
    for nm, _ in VAR:
        ds, R = CURVES[nm]; yrs = np.array([d[:4] for d in ds]); idx = np.where(yrs == y)[0]
        i0, i1 = max(idx[0]-1, 0), idx[-1]
        v = np.median([(r["curve"].to_numpy()[i1]/r["curve"].to_numpy()[i0]-1)*100 for r in R])
        row += f"{v:>+15.1f}%"
    print(row)
