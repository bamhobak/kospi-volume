# -*- coding: utf-8 -*-
"""새 패널의 2018~ 공매도 지표를 기존 패널에서 옮겨 붙인다.

새 패널은 DB(daily)만 읽어 만들었는데, 2018~ 구간의 공매도는 DB 가 아니라 별도
경로(short_recent.csv 등)로 관리돼 왔다. 그래서 srd 가 2018 이후 100% 비었고
공매도를 조건에 쓰는 규칙이 전부 0건이 됐다. 2016~2017 은 백필 때 KRX 에서
직접 받아 채워져 있으므로, 비어 있는 2018~ 만 기존 패널(kp_ow/kq_ow)에서 채운다.
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import pandas as pd
BASE = Path(__file__).parent
for new, old, nm in (("panel_kp.pkl","kp_ow.pkl","코스피"), ("panel_kq.pkl","kq_ow.pkl","코스닥")):
    K = pd.read_pickle(BASE/"data"/new)
    O = pd.read_pickle(BASE/"data"/old)[["ticker","date","sr20","srd"]]
    before = K.srd.isna().mean()*100
    M = K.merge(O, on=["ticker","date"], how="left", suffixes=("","_o"))
    assert len(M) == len(K), f"{nm}: 병합에서 행이 늘었다 — 키 중복"
    for c in ("sr20","srd"):
        M[c] = M[c].where(M[c].notna(), M[c+"_o"])      # 새 값이 있으면 그대로, 없으면 기존값
        M.drop(columns=[c+"_o"], inplace=True)
    after = M.srd.isna().mean()*100
    M.to_pickle(BASE/"data"/new)
    y = M.assign(y=M.date.str[:4]).groupby("y").srd.apply(lambda s: s.isna().mean()*100)
    print(f"  {nm}: srd 결측 {before:.0f}% → {after:.0f}%")
    print("    연도별 " + " ".join(f"{k}:{v:.0f}%" for k, v in y.items() if k >= "2016"))
