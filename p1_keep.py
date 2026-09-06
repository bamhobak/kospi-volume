# -*- coding: utf-8 -*-
"""[조용한 신고가] 를 둘 것인가 — 계좌로 답한다.

조율은 실패했다. 조건을 하나씩 빼도, 보유·손절을 바꿔도, 국면 게이트 다섯 가지도,
갈림길처럼 보였던 ret250·r16 문턱도 2009~2013 을 못 고쳤다(CI 하한 전부 0 근처·음수).
남은 물음은 하나다 — 이 규칙이 계좌에 있는 게 나은가, 빼거나 줄이는 게 나은가.
종목당 12%·최대 7종목으로 아홉 중 가장 크게 거는 규칙이라 자리 값이 비싸다.
사용: IX_FROM=2004-06-01 DART_FROM=20040101 PANEL_KP=panel_kp.pkl PANEL_KQ=panel_kq.pkl python p1_keep.py
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

def variant(drop=None, pct=None):
    R = {}
    for rid, v in RULES.items():
        if rid == drop: continue
        if rid == "P1" and pct: P,h,st,_,mx,c = v; R[rid] = (P,h,st,pct,mx,c)
        else: R[rid] = v
    return build(R)
VAR = [("현행 (12%·7종목)", variant()),
       ("비중 6% 로 축소", variant(pct=6)),
       ("비중 3% 로 축소", variant(pct=3)),
       ("규칙 제거", variant(drop="P1"))]
PER = [("2005~2017","20050101","20171231"), ("2018~2026","20180101","20991231"),
       ("전체 2005~","20050101","20991231")]
print(f"  {'안':<18}" + "".join(f"{p[0]:>26}" for p in PER))
print(f"  {'':<18}" + "".join(f"{'자산':>10}{'낙폭':>8}{'시드승':>8}" for p in PER))
print("  " + "-"*96)
BASE_N = {}
for nm, S in VAR:
    row = ""
    for pn, lo, hi in PER:
        ds = [d for d in adates if lo <= d <= hi]
        R = [sim(S, ds, k) for k in range(SEEDS)]
        nav = [r["nav"] for r in R]; mdd = np.median([r["mdd"] for r in R])
        if nm.startswith("현행"): BASE_N[pn] = nav; w = "기준"
        else: w = f"{sum(a>b for a,b in zip(nav, BASE_N[pn]))}/{SEEDS}"
        row += f"{np.median(nav):>9.2f}배{mdd:>7.0f}%{w:>8}"
    print(f"  {nm:<18}{row}")
