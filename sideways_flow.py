# -*- coding: utf-8 -*-
"""횡보장에서 거래할 길 — 기술적 진입 대신 '검증된 재료' 로.
(a) [외인 매집] 본체를 게이트 없이 횡보 국면에 풀어 본다 (지금은 코스피 60일선 위에서만 열린다)
(b) 수급만으로 고른다 — 외인·기관 누적 순매수 + 고점 근접, 가격 패턴 없이
판정은 techlib 게이트. 국면 SIDE = 코스피 60일선 이격 ±5%. 내부자(ins60)는 techlib 패널에 없어 뺐다."""
import numpy as np, pandas as pd, warnings; warnings.filterwarnings("ignore")
from techlib import *
P7 = ((A.marcap>=1e4)&(A.marcap<1e5)&(A.fw20>=1)&(A.ow60<0.4)&(A.r16>=100)&(A.r16<150)&(A.fromhi>=-15)&(A.fromlo>=70))
FLOW1 = (A.fw20>=2)&(A.ow20>=0)&(A.fromhi>=-15)&(A.r16.between(80,150))
FLOW2 = (A.fw60>=3)&(A.fw20>=1)&(A.ow60>=0)&(A.fromhi>=-20)
FLOW3 = (A.fw20>=1)&(A.ow20>=0)&(A.fromlo>=50)&(A.fromhi>=-10)
SETS = {"[외인매집] 본체(게이트·내부자 없이)": P7, "수급1 외인20일≥2·기관≥0·고점-15%": FLOW1,
        "수급2 외인60일≥3·기관60≥0": FLOW2, "수급3 외인·기관≥0·저점+50·고점-10": FLOW3}
SUB = {"SIDE 전체": (A.reg=="SIDE"), "SIDE·60일선 위(지금 열린 구간)": (A.reg=="SIDE")&(A.ixdev>0),
       "SIDE·60일선 아래(새로 여는 구간)": (A.reg=="SIDE")&(A.ixdev<=0), "SIDE·이격≥-3": (A.reg=="SIDE")&(A.ixdev>=-3)}
for hold in (20, 40, 60):
    for sn, sm in SUB.items():
        A["reg2"] = np.where(sm.fillna(False), "X", "-"); A["reg"], keep = A["reg2"], A["reg"].copy()
        print(f"\n━━ {sn} · 고정 {hold}일 · 유니버스 {base(hold, reg='X'):+.2f}% ━━"); hdr()
        for tag, c in SETS.items(): go(tag, c, hold=hold, reg="X", minn=25)
        A["reg"] = keep
