# -*- coding: utf-8 -*-
"""하락장 게이트를 좁혀 횡보장 신호를 걸러낸다 — 규칙 단위 실측.

지금 게이트는 '코스피 60일선 아래'(dn60) 인데, 이건 횡보장도 통과시킨다.
실측: 횡보 국면 324건 평균 +3.90% · 중앙값 +0.94% · 승률 54% 로 사실상 본전이고
[업종붕괴 이탈] 은 47건 +0.01% · 승률 38% 로 지는 쪽이다. 횡보장이 전체의 73% 다.

게이트를 '60일선 이격 X% 이하' 로 좁히면 그 구간이 걸러진다. 대신 신호도 준다.
문턱을 옮겨 가며 규칙별로 잰다. 학습(2018~22)에서 고르고 검증은 확인용이다.
사용: python gate_test.py
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
IX["d"] = IX.index.strftime("%Y%m%d"); IX["ma60"] = IX.Close.rolling(60).mean()
IX["dev"] = (IX.Close/IX.ma60 - 1)*100
DEV = dict(zip(IX.d, IX.dev))
UP60 = dict(zip(IX.d, IX.Close > IX.ma60)); UP20 = dict(zip(IX.d, IX.Close > IX.Close.rolling(20).mean()))

def load(f):
    K = pd.read_pickle(BASE/"data"/f).sort_values(["ticker","date"]).reset_index(drop=True)
    K["pref"] = ~K.ticker.str.endswith("0")
    K["up60"] = K.date.map(UP60).fillna(False); K["up20"] = K.date.map(UP20).fillna(False)
    K["kdev"] = K.date.map(DEV)                       # 코스피 60일선 이격
    g = K.groupby("ticker", sort=False)
    K["dev25"] = (K.close/g.close.transform(lambda s: s.rolling(25,min_periods=25).mean())-1)*100
    return K
KP, KQ = load("panel_kp.pkl"), load("panel_kq.pkl")
KB = pd.concat([KP,KQ], ignore_index=True).sort_values(["ticker","date"]).reset_index(drop=True)
def base(K,a): return (~K.pref)&(~K.dil.fillna(False))&(K.close>=1000)&(K.amt20>=a)

# 게이트를 뺀 '규칙 본체'. 게이트는 아래에서 갈아 끼운다.
CORE = {
 "업종붕괴 이탈": (KP,5,0.15, base(KP,10)&(KP.u<=-20)&(KP.dma20<=-10)&(KP.mdd60<=-40)&(KP.srd==True)),
 "깊은 이격":   (KP,5,0.10, base(KP,10)&(KP.dev25<=-25)&(KP.u<=-20)),
 "폭락반등":    (KP,20,None, base(KP,3)&(KP.ret20<=-20)&(KP.su1>=1.5)&(KP.fw60>=1)&(KP.u<=-10)&(KP.srd==True)),
 "낙폭과대":    (KQ,20,None, base(KQ,2)&(KQ.ret20<=-20)&(KQ.su1>=1.5)&(KQ.fw60>=1)&(KQ.u<=-20)
                 &(KQ.srd==True)&(KQ.ow20>=0)),
 "자사주 낙폭":  (KB,10,None, base(KB,3)&(KB.bb==True)&(KB.ret60<=-20)),
}
def trades(K,hold,stop,cond):
    g=K.groupby("ticker",sort=False); col=f"n{hold}"
    if stop:
        low=pd.concat([g.low.shift(-i) for i in range(hold)],axis=1).min(axis=1)
        r=np.where((low<=K.buy*(1-stop)).fillna(False),-stop*100-K.cost,K[col])
    else: r=K[col].values
    m=cond.fillna(False)
    X=K[m].copy(); X["_r"]=r[m.values]; X=X.dropna(subset=["_r"])
    d=sorted(K.date.unique()); di={x:i for i,x in enumerate(d)}
    X["di"]=X.date.map(di); X=X.sort_values("di")
    keep,last=[],{}
    for t,i,ix in zip(X.ticker.values,X.di.values,X.index):
        if last.get(t,-10**9)>=i: continue
        last[t]=i+hold; keep.append(ix)
    return X.loc[keep]
def stat(Z, lo, hi):
    S = Z[(Z.date>=lo)&(Z.date<=hi)]
    if len(S)<10: return f"{len(S):>5}건{'':>18}"
    v=S._r.to_numpy()
    return f"{len(S):>5}건{v.mean():>+7.2f}%{np.median(v):>+7.2f}%승{(v>0).mean()*100:>3.0f}%"

GATES = [("현재: 60일선 아래", 0.0), ("이격 ≤ -2%", -2.0), ("이격 ≤ -5%", -5.0),
         ("이격 ≤ -8%", -8.0), ("이격 ≤ -12%", -12.0)]
for nm,(K,hold,stop,core) in CORE.items():
    print(f"\n  [{nm}]")
    print(f"    {'게이트':<20}{'전체':>26}{'학습 2018~22':>26}{'검증 2023~26':>26}")
    for gn, thr in GATES:
        gate = (K.kdev < 0) if thr == 0 else (K.kdev <= thr)
        Z = trades(K, hold, stop, core & gate)
        print(f"    {gn:<20}{stat(Z,'20160101','20991231'):>26}{stat(Z,'20180101','20221231'):>26}"
              f"{stat(Z,'20230101','20991231'):>26}")
