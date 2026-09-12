# -*- coding: utf-8 -*-
"""미장 축 정찰용 슬림 패널. panel_us(11.5GB)에서 필요한 열만 뽑아 둔다."""
import io,sys,gc,time,warnings; warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE=Path(__file__).parent
def log(m): print(f"{time.strftime('%H:%M:%S')} {m}",flush=True)
COLS=["date","ticker","mk","px","close","volume","amt20","buy","cost","pref","up","u",
      "n5","n10","n20","n40","n60",
      "dma5","dma20","dma60","dma120","ret3","ret5","ret10","ret20","ret60","ret120","ret250",
      "fromhi","fromlo","dd","mdd60","above20","dev25","vol20","rng","clv","gap",
      "vm1","vm3","a40","a240","r16","rw1","su1","PBR","PER","부채비율","marcap","sr20","srd"]
log("panel_us.pkl 읽는 중")
K=pd.read_pickle(BASE/"data/panel_us.pkl")
K=K[[c for c in COLS if c in K.columns]].copy(); gc.collect()
K=K.rename(columns={"close":"rawclose","px":"close"})
for c in K.columns:
    if K[c].dtype==np.float64: K[c]=K[c].astype("float32")
K=K.sort_values(["ticker","date"]).reset_index(drop=True)

# ⚠ panel_us.pkl(마스터)는 2026-09-12 감사 이전에 만들어진 것일 수 있다. 그대로 뽑으면
#   수리한 us_scan.pkl 이 **통째로 되돌아간다**. us_panel.py 에 가드를 넣어 뒀지만 마스터를
#   다시 빌드하기 전까지는 여기서 같은 수리를 다시 한다(멱등하다 — 이미 깨끗하면 0건).
#     ① 수정주가 ≤0 종목 제거(yfinance adj 계수가 음수였던 VATE·CBIO·DEC)
#     ② 다음 거래일 공백·다음날 거래량 0 → 매수 불가
#     ③ 보유 구간이 공백을 지나거나 파는 날 거래량이 0 → 선행수익 결측
#     ④ 반쪽 수집일(패널 꼬리) 제거
_bad=sorted(set(K.loc[(K.close<=0)|(K.buy<=0),"ticker"]))
if _bad:
    log(f"  ① 수정주가 ≤0 종목 {len(_bad)}개 제거 {_bad[:6]}")
    K=K[~K.ticker.isin(_bad)]
_cnt=K.groupby("date").size(); _med=_cnt.rolling(60,min_periods=20).median()
_thin=_cnt[(_cnt<_med*0.6)].index
if len(_thin):
    log(f"  ④ 반쪽 수집일 {len(_thin)}일 제거 {list(_thin)[:4]}")
    K=K[~K.date.isin(_thin)]
K=K.sort_values(["ticker","date"]).reset_index(drop=True)
_ud=sorted(K.date.unique()); _DI={d:i for i,d in enumerate(_ud)}
_pos=K.date.map(_DI).astype(np.int64); _g=K.groupby("ticker",sort=False)
_nxt=_g.date.shift(-1).map(_DI); _last=_g.date.transform("max").map(_DI)
_buybad=((_nxt-_pos!=1)&(_pos!=_last))|(_g.volume.shift(-1).fillna(0)<=0)
_fix=0
for _h in (5,10,20,40,60):
    _c=f"n{_h}"
    if _c not in K.columns: continue
    _sp=_g.date.shift(-_h).map(_DI)
    _span=((_pos+_h)<=_last)&(_sp-_pos!=_h)
    _sv0=(_g.volume.shift(-_h).fillna(1)<=0)
    _m=(_buybad|_span|_sv0)&K[_c].notna()
    K.loc[_m,_c]=np.nan; _fix+=int(_m.sum())
K.loc[_buybad,"buy"]=np.nan
log(f"  ②③ 매수 불가 {int(_buybad.sum()):,}행 · 선행수익 결측 처리 {_fix:,}칸")

K.to_pickle(BASE/"data/us_scan.pkl")
log(f"저장 data/us_scan.pkl · {len(K):,}행 · 열 {len(K.columns)}")
