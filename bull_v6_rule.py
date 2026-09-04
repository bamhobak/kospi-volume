# -*- coding: utf-8 -*-
"""V6(게이트 +8 · 내부자 ≥3) 규칙 단위 재검증 — 이웃(게이트 × 내부자) · 연도별 성적 · 빈도."""
import numpy as np, pandas as pd, warnings; warnings.filterwarnings("ignore")
from techlib import *
O = pd.read_pickle(BASE/"data/insider_feat.pkl")[["ticker","date","ins60"]]
T = A.merge(O, on=["ticker","date"], how="left"); A["ins60"] = T.ins60.fillna(0).values; del T, O
core = (A.dma60>0)&(A.fromhi>=-15)&(A.fw20<1)&(A.vol20<=3)
keep = A["reg"].copy()
print("이웃 — 게이트 이격 × 내부자 건수 · 코스피 · 60일"); hdr()
for gv in (6, 8, 10):
    A["reg"] = np.where((A.ixdev>gv).fillna(False), "X", "-")
    for k in (2, 3, 4):
        go(f"이격>{gv} · ins≥{k}", core&(A.ins60>=k), hold=60, mk="KOSPI", reg="X", minn=25)
A["reg"] = np.where((A.ixdev>8).fillna(False), "X", "-")
print("\n변동성·고점 이웃 (이격>8 · ins≥3)"); hdr()
for v in (2, 3, 4): go(f"vol20≤{v}", (A.dma60>0)&(A.fromhi>=-15)&(A.fw20<1)&(A.vol20<=v)&(A.ins60>=3), hold=60, mk="KOSPI", reg="X", minn=25)
for fh in (-10, -15, -20): go(f"고점≥{fh}", (A.dma60>0)&(A.fromhi>=fh)&(A.fw20<1)&(A.vol20<=3)&(A.ins60>=3), hold=60, mk="KOSPI", reg="X", minn=25)
Y = go("V6 (이격>8·ins≥3·vol≤3·고점-15)", core&(A.ins60>=3), hold=60, mk="KOSPI", reg="X", minn=25)
yr = Y.groupby("yr").agg(n=("r","size"), avg=("r","mean"), win=("r", lambda s: (s>0).mean()*100), alpha=("alpha","mean"))
print("\nV6 연도별 (규칙 단위 · 60일)")
for y, r in yr.iterrows(): print(f"  {y}  {int(r.n):>4}건  평균 {r.avg:>+6.2f}%  승률 {r.win:>3.0f}%  초과 {r.alpha:>+5.2f}")
mon = Y.ym.nunique(); opn = A.loc[A.reg=="X","date"].str[:6].nunique()
print(f"\n빈도: 거래 {len(Y)}건 · 신호 난 달 {mon}개월 · 게이트 열린 달 {opn}개월(전체 {A.date.str[:6].nunique()}개월) · 열린 달 평균 {len(Y)/max(opn,1):.1f}건")
A["reg"] = keep
