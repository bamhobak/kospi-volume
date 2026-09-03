# -*- coding: utf-8 -*-
"""2016~2017 구간에서 규칙이 통하는가 — 새로 받은 백필 데이터로 처음 재는 것.

왜 중요한가: [업종붕괴 이탈] 은 실거래 775건의 절반이 2020년 3월 코로나 폭락
3주에서 나왔다. 그 사건은 '며칠 만에 -30%, 이후 V자 반등' 이라는 특수한 형태다.
2016년은 코스피 60일선 아래가 연중 43% 였지만 완만한 하락장이었다. 성격이 다른
하락장에서도 통하면 규칙이고, 안 통하면 그 3주 전용이었다는 뜻이다.

사용: python test_2016.py
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd, FinanceDataReader as fdr
BASE = Path(__file__).parent

# 코스피 지수 게이트 (FDR 은 3,000행 상한이라 나눠 받는다)
parts = [fdr.DataReader("KS11", a, b) for a, b in
         (("2015-01-01","2019-12-31"), ("2020-01-01","2026-09-03"))]
IX = pd.concat(parts); IX = IX[~IX.index.duplicated()].sort_index(); IX = IX[IX.Close > 0]
IX["d"] = IX.index.strftime("%Y%m%d")
UP60 = dict(zip(IX.d, IX.Close > IX.Close.rolling(60).mean()))
UP20 = dict(zip(IX.d, IX.Close > IX.Close.rolling(20).mean()))

K = pd.read_pickle(BASE/"data"/"panel_kp.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
K["pref"] = ~K.ticker.str.endswith("0")
K["up60"] = K.date.map(UP60).fillna(False)
K["up20"] = K.date.map(UP20).fillna(False)
NO = ~K.dil.fillna(False)
BASECOND = (~K.pref) & NO & (K.close >= 1000)

RULES = {
 "업종붕괴 이탈": (5, 0.15, BASECOND & (K.amt20>=10) & (~K.up60) & (K.u<=-20)
                  & (K.dma20<=-10) & (K.mdd60<=-40) & (K.srd==True)),
 "조정매집":     (10, None, BASECOND & (K.amt>=3) & (~K.up20) & (K.r16<30) & (K.rw1>=200)
                  & (K.fw5>=2) & (K.ret3<=-5) & (K.ret10<=0) & (K.srd==True)),
 "조용한 신고가": (40, 0.15, BASECOND & (K.amt20>=200) & (K.fromhi>=-10) & (K.r16<120)
                  & (K.rw1<=120) & (K.fw5>=3) & (K.fw60>=1) & (K.vol20<=2)
                  & (K.sr20<=0.5) & (K.ret20<=5)),
}
def measure(hold, stop, cond, lo, hi):
    g = K.groupby("ticker", sort=False)
    col = f"n{hold}"
    if stop:
        low = pd.concat([g.low.shift(-i) for i in range(hold)], axis=1).min(axis=1)
        r = np.where((low <= K.buy*(1-stop)).fillna(False), -stop*100 - K.cost, K[col])
    else: r = K[col].values
    m = cond.fillna(False) & (K.date >= lo) & (K.date <= hi)
    X = K[m].copy(); X["_r"] = r[m.values]
    X = X.dropna(subset=["_r"])
    d = sorted(K.date.unique()); di = {x:i for i,x in enumerate(d)}
    X["di"] = X.date.map(di); X = X.sort_values("di")
    keep, last = [], {}
    for t,i,ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t,-10**9) >= i: continue
        last[t] = i+hold; keep.append(ix)
    return X.loc[keep]

PER = [("2016~2017 (새로 받은 구간)","20160101","20171231"),
       ("2018~2022 (학습)","20180101","20221231"),
       ("2023~2026 (검증)","20230101","20991231"),
       ("2020년 3월만","20200301","20200331")]
for nm,(hold,stop,cond) in RULES.items():
    print(f"\n  [{nm}] · {hold}거래일" + (f" · 손절 -{stop*100:.0f}%" if stop else ""))
    print(f"    {'구간':<24}{'건수':>6}{'평균':>9}{'승률':>7}{'중앙':>9}{'최악':>9}")
    for pn,lo,hi in PER:
        Z = measure(hold, stop, cond, lo, hi)
        if not len(Z): print(f"    {pn:<24}{0:>6}"); continue
        v = Z._r.to_numpy()
        print(f"    {pn:<24}{len(Z):>6}{v.mean():>+8.2f}%{(v>0).mean()*100:>6.0f}%"
              f"{np.median(v):>+8.2f}%{v.min():>+8.1f}%")
