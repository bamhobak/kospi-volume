# -*- coding: utf-8 -*-
"""[저PBR 낙폭] 이 2005~2009 에 0건인 이유 — 조건이 안 걸린 건가, 재료가 없는 건가.

PBR 을 붙이자 2010년부터는 신호가 나기 시작했다. 그 앞 5년이 여전히 비어 있는데,
'그때는 조건에 맞는 종목이 없었다' 와 '그때 재료를 못 받았다' 는 전혀 다른 이야기다.
조건을 하나씩 켜 가며 몇 건이 살아남는지 연도별로 센다.
사용: IX_FROM=2004-06-01 DART_FROM=20040101 PANEL_KP=panel_kp.pkl PANEL_KQ=panel_kq.pkl python d2_gap.py
"""
import io, os, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KQ, base, dn60 = ns["KQ"], ns["base"], ns["dn60"]
KQ["_y"] = KQ.date.str[:4]
YRS = [str(y) for y in range(2005, 2027)]

STEPS = [("기본(거래대금5억·주가1000)", base(KQ,5)),
         ("+ 하락장(코스피60일선↓)",    dn60(KQ)),
         ("+ PBR 0~0.5",              (KQ.PBR>0)&(KQ.PBR<=0.5)),
         ("+ 20일 낙폭 ≤-10%",         KQ.ret20<=-10),
         ("+ 당일 거래량 ≥2배",          KQ.su1>=2),
         ("+ 업종 60일 ≤-10%",         KQ.u<=-10),
         ("+ 기관 20일 ≥0",            KQ.ow20>=0),
         ("+ 공매도 감소(srd)",         KQ.srd==True)]
print("[저PBR 낙폭] 조건을 하나씩 켜면 남는 신호 수 (연도별)")
print(f"  {'조건':<26}" + "".join(f"{y[2:]:>6}" for y in YRS))
print("  " + "-"*(26+6*len(YRS)))
cur = pd.Series(True, index=KQ.index)
for nm, c in STEPS:
    cur = cur & c.fillna(False)
    n = KQ[cur].groupby("_y").size()
    print(f"  {nm:<26}" + "".join(f"{n.get(y,0):>6,}" for y in YRS))

print("\n재료 유효율(%) — 값이 있는 행의 비율")
for c, nm in (("PBR","PBR"), ("ow20","기관20일"), ("srd","공매도감소"), ("u","업종60일"),
              ("su1","당일거래량"), ("amt20","거래대금")):
    if c not in KQ.columns: print(f"  {nm:<12} 열 없음"); continue
    r = KQ.groupby("_y")[c].apply(lambda s: s.notna().mean()*100)
    print(f"  {nm:<12}" + "".join(f"{r.get(y,0):>6.0f}" for y in YRS))
