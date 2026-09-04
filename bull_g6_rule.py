# -*- coding: utf-8 -*-
"""G6·ins≥3 규칙 단위 — 연도별 · 빈도 · 게이트 열린 달."""
import numpy as np, pandas as pd, warnings; warnings.filterwarnings("ignore")
from techlib import *
O = pd.read_pickle(BASE/"data/insider_feat.pkl")[["ticker","date","ins60"]]
T = A.merge(O, on=["ticker","date"], how="left"); A["ins60"] = T.ins60.fillna(0).values; del T, O
core = (A.dma60>0)&(A.fromhi>=-15)&(A.fw20<1)&(A.vol20<=3)
for gv, k in ((6,3),(6,2),(5,2)):
    A["reg"] = np.where((A.ixdev>gv).fillna(False), "X", "-")
    print(f"\n이격>{gv} · ins≥{k}"); hdr()
    Y = go(f"이격>{gv}·ins≥{k}", core&(A.ins60>=k), hold=60, mk="KOSPI", reg="X", minn=25)
    yr = Y.groupby("yr").agg(n=("r","size"), avg=("r","mean"), win=("r", lambda s: (s>0).mean()*100), alpha=("alpha","mean"))
    for y, r in yr.iterrows(): print(f"  {y}  {int(r.n):>4}건  평균 {r.avg:>+6.2f}%  승률 {r.win:>3.0f}%  초과 {r.alpha:>+5.2f}")
    opn = A.loc[A.reg=="X","date"].str[:6].nunique()
    print(f"  빈도: {len(Y)}건 · 신호 달 {Y.ym.nunique()} · 게이트 열린 달 {opn}/{A.date.str[:6].nunique()} · 열린 달 평균 {len(Y)/max(opn,1):.1f}건")
