# -*- coding: utf-8 -*-
"""국내 축 정찰용 슬림 패널 — us_scan.pkl 과 같은 열 구성으로 맞춘다(나란히 놓기 위해)."""
import io,sys,gc,time,warnings; warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE=Path(__file__).parent
def log(m): print(f"{time.strftime('%H:%M:%S')} {m}",flush=True)
COLS=["date","ticker","open","high","low","close","volume","amt20","buy","cost","up","u",
      "n5","n10","n20","n40","n60","dma5","dma20","dma60","dma120",
      "ret3","ret5","ret10","ret20","ret60","ret120","fromhi","fromlo","dd","mdd60",
      "vol20","rng","clv","gap","vm1","vm3","a40","a240","r16","rw1","su1",
      "PBR","PER","부채비율","marcap","sr20","srd","dil"]
out=[]
for f,mk in (("panel_kp.pkl","KOSPI"),("panel_kq.pkl","KOSDAQ")):
    log(f"{f} 읽는 중")
    K=pd.read_pickle(BASE/"data"/f)
    K=K[[c for c in COLS if c in K.columns]].copy(); K["mk"]=mk
    out.append(K); del K; gc.collect()
A=pd.concat(out,ignore_index=True); del out; gc.collect()
A["pref"]=~A.ticker.str.endswith("0")
A=A.sort_values(["ticker","date"]).reset_index(drop=True)
g=A.groupby("ticker",sort=False)
# 미국 패널에 있는데 국내에 없는 파생 두 개를 같은 정의로 만든다
A["ret250"]=(A.close/g.close.shift(250)-1)*100
A["dev25"]=(A.close/g.close.transform(lambda s: s.rolling(25,min_periods=25).mean())-1)*100
# jw — 미조정 가격 점프(감자·병합·분할·이음새) 뒤 250거래일 창. 이 안의 과거 피처(ret·dev25·
# fromhi·dd)는 가짜다(2026-09-12 감사: dev25≤-25 신호의 18.9% 가 이 창 안). 연구 스크립트는
# `K[~K.jw]` 로 뺀다. portfolio.py 는 같은 정의를 자체 계산한다(MASKJUMP).
_pc=g.close.shift(1); _lim=np.where(A.date.values<"20150615",0.15,0.30)+0.10
_ca=(_pc.notna()&((A.close/_pc>1+_lim)|(A.close/_pc<1-_lim))).astype(np.int32)
_cs=_ca.groupby(A.ticker).cumsum()
A["jw"]=((_cs-_cs.groupby(A.ticker).shift(250).fillna(0))>0).values
# 이음새 잔여 종목(폐지라 네이버 수정주가가 없어 fix_panels 가 경계 비율로 곱한 것)은 점프가
# 사라졌지만 2018 의 과거 피처는 빌드 때 옛 기준으로 계산된 채다 → 2018-01-02 부터 250행을 창으로
_sr=BASE/"data/seam_residual.csv"
if _sr.exists():
    _st=set(pd.read_csv(_sr,dtype={"ticker":str}).ticker)
    _in=A.ticker.isin(_st)&(A.date>="20180102")
    _rk=_in.groupby(A.ticker).cumsum()
    A.loc[_in&(_rk<=250),"jw"]=True
    log(f"  이음새 잔여 {len(_st)}종목 → 2018 첫 250행 창 추가")
log(f"  점프 뒤 250일 창(jw) {int(A.jw.sum()):,}행 ({A.jw.mean()*100:.2f}%)")
ma20=g.close.transform(lambda s: s.rolling(20).mean())
A["above20"]=(A.close>ma20).groupby(A.ticker).transform(lambda s: s.rolling(250,min_periods=60).mean())*100
for c in A.columns:
    if A[c].dtype==np.float64: A[c]=A[c].astype("float32")
A.to_pickle(BASE/"data/kr_scan.pkl")
log(f"저장 data/kr_scan.pkl · {len(A):,}행 · 열 {len(A.columns)}")
