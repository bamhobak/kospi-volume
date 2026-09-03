# -*- coding: utf-8 -*-
"""새로 받은 2016~2017 구간에서 규칙이 통하는가 — 전 규칙 측정.

빠진 조건은 그대로 밝힌다(없는 걸 있는 척하면 비교가 거짓이 된다):
  · [폭락반등]  신용잔고(crc) 미수집 → 그 조건 없이 측정
  · [낙폭과대]  부채비율 2018~ 만 있음 → 원 규칙도 '없으면 통과' 라 영향 없음
  · [저PBR 낙폭] PBR 미수집 → 측정 불가(필수 조건)
  · [조용한 신고가] above20·ret250 미계산 → 그 조건 없이 측정(느슨해짐)

사용: python test_hist.py
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd, FinanceDataReader as fdr
BASE = Path(__file__).parent

parts = [fdr.DataReader("KS11", a, b) for a, b in
         (("2015-01-01","2019-12-31"), ("2020-01-01","2026-09-03"))]
IX = pd.concat(parts); IX = IX[~IX.index.duplicated()].sort_index(); IX = IX[IX.Close > 0]
IX["d"] = IX.index.strftime("%Y%m%d")
UP60 = dict(zip(IX.d, IX.Close > IX.Close.rolling(60).mean()))
UP20 = dict(zip(IX.d, IX.Close > IX.Close.rolling(20).mean()))

def load(f):
    K = pd.read_pickle(BASE/"data"/f).sort_values(["ticker","date"]).reset_index(drop=True)
    K["pref"] = ~K.ticker.str.endswith("0")
    K["up60"] = K.date.map(UP60).fillna(False)
    K["up20"] = K.date.map(UP20).fillna(False)
    return K
KP, KQ = load("panel_kp.pkl"), load("panel_kq.pkl")
KB = pd.concat([KP, KQ], ignore_index=True).sort_values(["ticker","date"]).reset_index(drop=True)

def base(K, amt): return (~K.pref) & (~K.dil.fillna(False)) & (K.close >= 1000) & (K.amt20 >= amt)
R = {}
R["외인 매집"]      = (KP, 60, None, base(KP,30) & KP.up60 & (KP.marcap>=1e4*1e8) & (KP.marcap<1e5*1e8)
                       & (KP.fw20>=1) & (KP.ow60<0.4) & (KP.r16>=100) & (KP.r16<150)
                       & (KP.fromhi>=-15) & (KP.fromlo>=70) & (KP.ins60.fillna(0)>0))
R["조용한 신고가"]   = (KP, 40, 0.15, base(KP,200) & (KP.fromhi>=-10) & (KP.r16<120) & (KP.rw1<=120)
                       & (KP.fw5>=3) & (KP.fw60>=1) & (KP.vol20<=2) & (KP.sr20<=0.5) & (KP.ret20<=5))
R["업종붕괴 이탈"]   = (KP, 5, 0.15, base(KP,10) & (~KP.up60) & (KP.u<=-20) & (KP.dma20<=-10)
                       & (KP.mdd60<=-40) & (KP.srd==True))
R["깊은 이격"]      = (KP, 5, 0.10, base(KP,10) & (~KP.up60) & (KP.dma20<=-25) & (KP.u<=-20))
R["폭락반등"]       = (KP, 20, None, base(KP,3) & (KP.ret20<=-20) & (KP.su1>=1.5) & (KP.fw60>=1)
                       & (~KP.up60) & (KP.u<=-10) & (KP.srd==True))
R["조정매집"]       = (KP, 10, None, base(KP,3) & (~KP.up20) & (KP.r16<30) & (KP.rw1>=200)
                       & (KP.fw5>=2) & (KP.ret3<=-5) & (KP.ret10<=0) & (KP.srd==True))
R["낙폭과대"]       = (KQ, 20, None, base(KQ,2) & (KQ.ret20<=-20) & (KQ.su1>=1.5) & (KQ.fw60>=1)
                       & (~KQ.up60) & (KQ.u<=-20) & (KQ.srd==True) & (KQ.ow20>=0))
R["자사주 낙폭"]     = (KB, 10, None, (~KB.pref) & (KB.bb==True) & (KB.ret60<=-20) & (~KB.up60))

def measure(K, hold, stop, cond, lo, hi):
    g = K.groupby("ticker", sort=False); col = f"n{hold}"
    if stop:
        low = pd.concat([g.low.shift(-i) for i in range(hold)], axis=1).min(axis=1)
        r = np.where((low <= K.buy*(1-stop)).fillna(False), -stop*100 - K.cost, K[col])
    else: r = K[col].values
    m = cond.fillna(False) & (K.date>=lo) & (K.date<=hi)
    X = K[m].copy(); X["_r"] = r[m.values]; X = X.dropna(subset=["_r"])
    d = sorted(K.date.unique()); di = {x:i for i,x in enumerate(d)}
    X["di"] = X.date.map(di); X = X.sort_values("di")
    keep, last = [], {}
    for t,i,ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t,-10**9) >= i: continue
        last[t] = i+hold; keep.append(ix)
    return X.loc[keep]

PER = [("2016~2017 (신규)","20160101","20171231"), ("2018~2022 (학습)","20180101","20221231"),
       ("2023~2026 (검증)","20230101","20991231")]
print(f"  {'규칙':<15}" + "".join(f"{p[0]:>26}" for p in PER))
print("  " + "-"*93)
for nm, (K, hold, stop, cond) in R.items():
    cells = ""
    for _, lo, hi in PER:
        Z = measure(K, hold, stop, cond, lo, hi)
        if len(Z):
            v = Z._r.to_numpy()
            cells += f"{len(Z):>7}건 {v.mean():>+7.2f}% 승{(v>0).mean()*100:>3.0f}%"
        else:
            cells += f"{'신호 없음':>24}"
    print(f"  {nm:<15}{cells}")
print("\n  ※ 빠진 조건: [폭락반등] 신용잔고 · [조용한 신고가] 지속상승 배제 · [저PBR 낙폭] 은 PBR 미수집으로 제외")
