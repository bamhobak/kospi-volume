# -*- coding: utf-8 -*-
"""[외인 매집] 을 횡보장에 열어도 되는가 — 이번엔 내부자 조건(ins60>0) 을 붙여서.
앞선 sideways_flow.py 는 techlib 패널에 ins60 이 없어 그 조건을 뺀 채 쟀다. insider_feat.pkl(운영 규칙이 쓰는 그 값)에서 붙인다."""
import numpy as np, pandas as pd, warnings; warnings.filterwarnings("ignore")
from techlib import *
O = pd.read_pickle(BASE/"data/insider_feat.pkl")[["ticker","date","ins60"]]
n0 = len(A); A2 = A.merge(O, on=["ticker","date"], how="left"); assert len(A2)==n0
A["ins60"] = A2.ins60.values; del A2, O
print(f"ins60 결측(코스피 행): {A.loc[A.mk=='KOSPI','ins60'].isna().mean()*100:.0f}%")
core = ((A.marcap>=1e4)&(A.marcap<1e5)&(A.fw20>=1)&(A.ow60<0.4)&(A.r16>=100)&(A.r16<150)&(A.fromhi>=-15)&(A.fromlo>=70))
SETS = {"본체(내부자 없이)": core, "본체+내부자 ins60>0 (=현행 규칙 조건)": core&(A.ins60.fillna(0)>0),
        "본체+내부자 ≥2건": core&(A.ins60.fillna(0)>=2)}
SUB = {"SIDE 전체": (A.reg=="SIDE"), "SIDE·60일선 위 (현행 허용)": (A.reg=="SIDE")&(A.ixdev>0),
       "SIDE·60일선 아래 (새로 열기)": (A.reg=="SIDE")&(A.ixdev<=0), "참고: UP 국면 (현행 주무대)": (A.reg=="UP")}
keep = A["reg"].copy()
for hold in (40, 60):
    for sn, sm in SUB.items():
        A["reg"] = np.where(sm.fillna(False), "X", "-")
        print(f"\n━━ {sn} · 고정 {hold}일 · 유니버스 {base(hold, reg='X'):+.2f}% ━━"); hdr()
        for tag, c in SETS.items(): go(tag, c, hold=hold, mk="KOSPI", reg="X", minn=20)
        A["reg"] = keep
