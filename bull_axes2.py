# -*- coding: utf-8 -*-
"""상승장 세 번째 축 — 2단계: 기존 규칙과 겹침 · 연도 쏠림 · 문턱 이웃 · 보유기간 민감도."""
import sqlite3, numpy as np, pandas as pd, warnings; warnings.filterwarnings("ignore")
from techlib import *
O = pd.read_pickle(BASE/"data/insider_feat.pkl")[["ticker","date","ins60"]]
T = A.merge(O, on=["ticker","date"], how="left"); A["ins60"] = T.ins60.fillna(0).values; del T, O
I = pd.read_pickle(BASE/"data/tech_ind.pkl"); A["rsi"], A["mgold2"] = I.rsi.values, I.mgold2.values; del I
up = A.dma60>0; G5 = (A.ixdev>5); G0 = (A.ixdev>0)
CAND = {
 "내부자1 ins≥2·추세·외인<1·저변동":  (A.ins60>=2)&up&(A.fromhi>=-15)&(A.fw20<1)&(A.vol20<=3),
 "내부자2 ins≥1·저점+50·120선위·침체": (A.ins60>=1)&(A.fromlo>=50)&(A.dma120>0)&(A.r16<120),
 "내부자4 ins≥3·추세":              (A.ins60>=3)&up&(A.fromhi>=-20),
 "기관1 기관20≥1·외인≥0·추세·고점-10": (A.ow20>=1)&(A.fw20>=0)&up&(A.fromhi>=-10),
 "강세1 clv≥0.7·보통거래량·20선위":     (A.clv>=0.7)&(A.body>=0)&A.v5.between(0.8*A.v20,1.5*A.v20)&(A.dma20>0)&(A.fromhi>=-10),
 "눌림2 눌림·거래량고갈·외인60≥1":      (A.dma60>0)&(A.dma120>0)&A.dma20.between(-6,0)&(A.v5<0.7*A.v20)&(A.fw60>=1)&(A.ret5<=0),
}
P7 = G0&(A.marcap>=1e4)&(A.marcap<1e5)&(A.fw20>=1)&(A.ow60<0.4)&A.r16.between(100,150)&(A.fromhi>=-15)&(A.fromlo>=70)&(A.ins60>0)
P1 = G0&(A.amt20>=200)&(A.fromhi>=-10)&(A.r16<120)&(A.fw5>=3)&(A.fw60>=1)&(A.vol20<=2)&(A.sr20<=0.5)&(A.ret20<=5)
def sigset(c):
    X = A[(BASEU&(A.mk=="KOSPI")&c).fillna(False)]
    d = {}
    for t, i in zip(X.ticker.values, X.di.values): d.setdefault(t, []).append(i)
    return {t: np.sort(v) for t, v in d.items()}
S7, S1 = sigset(P7), sigset(P1)
def overlap(Y, S):
    n = hit = 0
    for t, i in zip(Y.ticker.values, Y.di.values):
        n += 1; o = S.get(t)
        if o is not None:
            j = np.searchsorted(o, i-5)
            if j < len(o) and o[j] <= i+5: hit += 1
    return hit/n*100 if n else np.nan
keep = A["reg"].copy(); A["reg"] = np.where(G5.fillna(False), "X", "-")
print("2-a) 기존 상승장 규칙과 겹침(±5일) · 연도 쏠림 — G5 · 코스피 · 60일\n")
print(f"  {'후보':<32}{'거래':>5}{'P7겹침':>7}{'P1겹침':>7}{'최다年':>7}{'연도분포'}")
for tag, c in CAND.items():
    Y = go(tag, c, hold=60, mk="KOSPI", reg="X", quiet=True)
    yr = Y.yr.value_counts().sort_index()
    print(f"  {tag:<32}{len(Y):>5}{overlap(Y,S7):>6.0f}%{overlap(Y,S1):>6.0f}%{yr.max()/len(Y)*100:>6.0f}%  "
          + " ".join(f"{y[2:]}:{n}" for y, n in yr.items()))
print("\n2-b) 문턱 이웃 — 값을 옮겨도 살아남는가 (절벽이면 그 값에 맞춘 것이다) · G5 · 코스피 · 60일"); hdr()
for k in (1, 2, 3):
    for v in (2, 3, 4):
        go(f"내부자1 ins≥{k}·vol20≤{v}·외인<1", (A.ins60>=k)&up&(A.fromhi>=-15)&(A.fw20<1)&(A.vol20<=v), hold=60, mk="KOSPI", reg="X")
for fw in (0.5, 1, 2):
    go(f"내부자1 외인<{fw} (ins≥2·vol≤3)", (A.ins60>=2)&up&(A.fromhi>=-15)&(A.fw20<fw)&(A.vol20<=3), hold=60, mk="KOSPI", reg="X")
go("내부자1 외인 조건 제거", (A.ins60>=2)&up&(A.fromhi>=-15)&(A.vol20<=3), hold=60, mk="KOSPI", reg="X")
for ow in (0.5, 1, 2):
    for fh in (-5, -10, -15):
        go(f"기관1 ow20≥{ow}·고점≥{fh}", (A.ow20>=ow)&(A.fw20>=0)&up&(A.fromhi>=fh), hold=60, mk="KOSPI", reg="X")
print("\n2-c) 보유기간 민감도 · G5 · 코스피"); hdr()
for tag in ("내부자1 ins≥2·추세·외인<1·저변동", "기관1 기관20≥1·외인≥0·추세·고점-10", "내부자2 ins≥1·저점+50·120선위·침체"):
    for h in (20, 40, 60): go(f"{tag[:18]} [{h}일]", CAND[tag], hold=h, mk="KOSPI", reg="X")
print("\n2-d) 게이트 민감도 — 이격 +3/+5/+8 · 60일"); hdr()
for gv in (3, 5, 8):
    A["reg"] = np.where((A.ixdev>gv).fillna(False), "X", "-")
    for tag in ("내부자1 ins≥2·추세·외인<1·저변동", "기관1 기관20≥1·외인≥0·추세·고점-10"):
        go(f"{tag[:18]} [이격>{gv}]", CAND[tag], hold=60, mk="KOSPI", reg="X")
A["reg"] = keep
