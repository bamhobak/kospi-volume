# -*- coding: utf-8 -*-
"""[조용한 신고가] 의 공매도 조건(sr20 ≤ 0.5) 을 어떻게 할 것인가.

발견: 이 조건이 신호를 2,269행→290행(13%)으로 줄이는데, 남는 13% 가 공매도
전면금지 기간(2020-03~2021-05 · 2023-11~2025-03)에 쏠려 있다. 신호가 난 해는
2020·2021·2023·2024·2025 뿐이고 공매도가 정상이던 2017·2018·2019·2022·2026 은 0 이다.
'공매도 표적이 아닌 종목' 을 고르려던 조건이 '공매도가 제도로 막힌 시기' 를
고르고 있었다. 2025-03 정상화 이후 신호는 0 이다 — 규칙이 사실상 죽어 있다.

무엇을 재나: 문턱을 옮기거나(0.5→1·2·3) 빼거나, 시장 대비 상대값으로 바꿨을 때
 · 신호가 공매도 정상기에도 나는가 (금지기 편중이 풀리는가)
 · 성적이 유지되는가 (학습에서 고르고 검증은 확인용)
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd, FinanceDataReader as fdr
BASE = Path(__file__).parent
parts=[fdr.DataReader("KS11",a,b) for a,b in (("2015-01-01","2019-12-31"),("2020-01-01","2026-09-03"))]
IX=pd.concat(parts); IX=IX[~IX.index.duplicated()].sort_index(); IX=IX[IX.Close>0]
K = pd.read_pickle(BASE/"data"/"panel_kp.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
K["pref"] = ~K.ticker.str.endswith("0")
# 공매도 전면금지 구간 — 이 시기 신호는 제도 때문에 생긴 것일 수 있다
BAN = ((K.date>="20200316")&(K.date<="20210502")) | ((K.date>="20231106")&(K.date<="20250331"))
K["ban"] = BAN
# 시장 대비 상대 공매도 — 그날 전체 종목의 중앙값 대비 몇 배인가.
# 금지기에는 모두가 낮아지므로 상대값은 제도 영향을 상당 부분 지운다.
med = K.groupby("date").sr20.transform("median")
K["sr_rel"] = K.sr20 / med.replace(0, np.nan)
CORE = ((~K.pref)&(~K.dil.fillna(False))&(K.close>=1000)&(K.amt20>=200)&(K.fromhi>=-10)
        &(K.r16<120)&(K.rw1<=120)&(K.fw5>=3)&(K.fw60>=1)&(K.vol20<=2)&(K.ret20<=5))
def trades(cond, hold=40, stop=0.15):
    g=K.groupby("ticker",sort=False)
    low=pd.concat([g.low.shift(-i) for i in range(hold)],axis=1).min(axis=1)
    r=np.where((low<=K.buy*(1-stop)).fillna(False),-stop*100-K.cost,K[f"n{hold}"])
    m=cond.fillna(False)
    X=K[m].copy(); X["_r"]=r[m.values]; X=X.dropna(subset=["_r"])
    d=sorted(K.date.unique()); di={x:i for i,x in enumerate(d)}
    X["di"]=X.date.map(di); X=X.sort_values("di")
    keep,last=[],{}
    for t,i,ix in zip(X.ticker.values,X.di.values,X.index):
        if last.get(t,-10**9)>=i: continue
        last[t]=i+hold; keep.append(ix)
    return X.loc[keep]
def line(nm, cond):
    Z=trades(cond)
    if len(Z)<5: print(f"  {nm:<26}{len(Z):>5}건  (표본 부족)"); return
    v=Z._r.to_numpy(); nb=Z[~Z.ban]; b=Z[Z.ban]
    zi=Z[Z.date<"20230101"]; zo=Z[Z.date>="20230101"]
    yrs=Z.date.str[:4].nunique()
    print(f"  {nm:<26}{len(Z):>5}건{v.mean():>+7.2f}%승{(v>0).mean()*100:>3.0f}%"
          f"│금지기{len(b):>4}건{(len(b)/len(Z)*100):>4.0f}%│정상기{len(nb):>4}건"
          + (f"{nb._r.mean():>+7.2f}%" if len(nb)>=5 else f"{'':>8}")
          + f"│학습{zi._r.mean() if len(zi) else float('nan'):>+6.2f}% 검증{zo._r.mean() if len(zo) else float('nan'):>+6.2f}%│{yrs}개년")
print("  전체 성적                        금지기 비중        공매도 정상기      학습/검증")
print(f"  {'조건':<26}{'건수':>5}{'평균':>8}{'승률':>5}│{'':>16}│")
line("현재: sr20 ≤ 0.5", CORE & (K.sr20<=0.5))
line("sr20 ≤ 1", CORE & (K.sr20<=1))
line("sr20 ≤ 2", CORE & (K.sr20<=2))
line("sr20 ≤ 3", CORE & (K.sr20<=3))
line("공매도 조건 제거", CORE)
line("상대 공매도 ≤ 0.5배(중앙값 대비)", CORE & (K.sr_rel<=0.5))
line("상대 공매도 ≤ 1배", CORE & (K.sr_rel<=1))
line("상대 공매도 ≤ 1.5배", CORE & (K.sr_rel<=1.5))
