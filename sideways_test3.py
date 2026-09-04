# -*- coding: utf-8 -*-
"""횡보 정의를 바꿔도 같은가 — ±5% 이격 대신 (a) ±3% 로 좁힌 횡보, (b) 지수 20일 박스폭 <6% 인 '진짜 박스'.
5개 기법이 횡보에서 지는 게 정의 탓인지 본다. 사용: python sideways_test3.py"""
import numpy as np, pandas as pd, FinanceDataReader as fdr, warnings; warnings.filterwarnings("ignore")
from techlib import *
I = pd.read_pickle(BASE/"data/tech_ind.pkl"); assert len(I)==len(A)
for c in I.columns:
    if c not in ("ticker","date"): A[c] = I[c].values
del I
ix = pd.concat([fdr.DataReader("KS11",a,b) for a,b in (("2017-01-01","2019-12-31"),("2020-01-01","2026-09-04"))])
ix = ix[~ix.index.duplicated()].sort_index(); ix = ix[ix.Close>0]
ix["d"] = ix.index.strftime("%Y%m%d")
ix["boxw"] = (ix.High.rolling(20).max().shift(1)-ix.Low.rolling(20).min().shift(1))/ix.Close
BOX = dict(zip(ix.d, ix.boxw))
A["ixbox"] = A.date.map(BOX)
up = (A.close>A.open); body=(A.close-A.open)/A.open; box_w=(A.hi20p-A.lo20p)/A.close
M = {
 "M1 스토+RSI+MACD":  (A.stk_min3<=20)&(A.rsi_prev<50)&(A.rsi>=50)&(A.mgold2)&(A.stk<80),
 "M2a 박스 지지반등":   box_w.between(0.05,0.25)&(A.low<=A.lo20p*1.02)&(A.close>A.lo20p)&up,
 "M2b 압축 돌파":     (A.bbw<=A.bbw_p20)&(A.close>A.hi20p)&(A.volume>2*A.v20)&(body>=0.02),
 "M3 볼린저 하단반등":  ((A.low<=A.bb_dn)|(A.lo_prev<=A.bb_dn_prev))&(A.close>A.bb_dn)&(A.close>A.ma60),
 "M5 일목 구름지지":    (A.cgreen)&(A.close>A.ctop)&(A.ctop_touch3)&up,
}
REGS = {"TIGHT(이격 ±3%)": A.ixdev.between(-3,3), "BOX(지수 20일폭<6%)": A.ixbox<0.06,
        "TIGHT∩BOX": A.ixdev.between(-3,3)&(A.ixbox<0.06)}
for rn, mask in REGS.items():
    A["reg"] = np.where(mask.fillna(False), "X", "-")
    share = int(mask.fillna(False).sum()/len(A)*100)
    for hold in (10,20):
        print(f"\n━━ {rn} · 거래일 비중 {share}% · 고정 {hold}일 · 유니버스 {base(hold, reg='X'):+.2f}% ━━"); hdr()
        for tag,c in M.items(): go(tag, c, hold=hold, reg="X")
