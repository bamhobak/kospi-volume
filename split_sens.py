# -*- coding: utf-8 -*-
"""자르는 자리가 판정을 좌우하나 — 학습/검증 경계를 밀어가며 본다.

사용자 질문(2026-09-09): "학습기간을 바꾸면 안 되겠지?"
**결과를 본 뒤에 구간을 옮기는 건 안 된다** — 검증구간이 학습의 일부가 되어버린다.
그러나 '한 번 자른 걸로 판정한다' 는 것 자체는 고칠 수 있다. 먼저 지금 자른 자리가
실제로 판정을 흔드는지 확인한다. 경계를 2020~2024 로 밀어가며 같은 후보를 재본다.

  · 어디서 잘라도 검증이 음수면 → 자른 자리 문제가 아니다(진짜 실패)
  · 자르는 자리에 따라 부호가 뒤집히면 → 한 번 자르기가 위태롭다(워크포워드 필요)
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(".")

def load(f, tag):
    K = pd.read_pickle(BASE/"data"/f).sort_values(["ticker","date"]).reset_index(drop=True)
    L = pd.read_pickle(BASE/"data"/f"long_ret_{tag}.pkl")
    K = K.merge(L, on=["ticker","date"], how="left")
    K["pref"] = ~K.ticker.str.endswith("0")
    g = K.groupby("ticker", sort=False)
    K["ret250x"] = (K.close/g.close.shift(250)-1)*100
    K["dev25"] = (K.close/g.close.transform(lambda s: s.rolling(25,min_periods=25).mean())-1)*100
    return K
KP = load("panel_kp.pkl","kp"); KQ = load("panel_kq.pkl","kq")
def base(K, amt=3):
    return ((~K.pref)&(K.close>=1000)&(~K.dil.fillna(False))&(K.amt20.fillna(0)>=amt))

def dedup(K, m, h):
    X = K[m.fillna(False)].dropna(subset=[f"n{h}"]).copy()
    di = {d:i for i,d in enumerate(sorted(K.date.unique()))}
    X["di"] = X.date.map(di); X = X.sort_values("di")
    keep, last = [], {}
    for t,i,ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t,-10**9) >= i: continue
        last[t] = i+h; keep.append(ix)
    return X.loc[keep]

CAND = [
 ("장기 저PBR+고점-40 (코스닥 250일)", KQ, 250,
  lambda K: base(K)&(K.PBR>0)&(K.PBR<=0.5)&(K.fromhi<=-40)),
 ("장기 120일 -40% 낙폭 (코스닥 120일)", KQ, 120,
  lambda K: base(K)&(K.ret120<=-40)),
 ("우리 재료: 업종+이격 (코스피 5일)", KP, 5,
  lambda K: base(K)&(K.u<=-10)&(K.dev25<=-12)),
 ("우리 재료: 업종+이격 (코스닥 5일)", KQ, 5,
  lambda K: base(K)&(K.u<=-10)&(K.dev25<=-12)),
]
CUTS = ["20200101","20210101","20220101","20230101","20240101"]
print("="*118)
print("경계를 밀어가며 — 각 칸은 그 경계 **뒤쪽(검증)** 구간의 절대 수익 중앙값")
print("="*118)
print(f"  {'후보':<34}{'전체중앙':>10}" + "".join(f"{c[:4]+'~':>12}" for c in CUTS))
for nm, K, h, fn in CAND:
    X = dedup(K, fn(K), h)
    X = X[X.date >= "20160101"]
    col = f"n{h}"
    row = f"{X[col].median():>+9.2f}%"
    for c in CUTS:
        z = X[X.date >= c][col]
        row += f"{z.median():>+10.2f}%({len(z)})" if len(z) >= 20 else f"{'표본부족':>12}"
    print(f"  {nm:<34}{row}")
print()
print("  ※ 괄호는 그 구간의 신호 수. 부호가 경계마다 뒤집히면 한 번 자르기가 위태롭다는 뜻이다.")
