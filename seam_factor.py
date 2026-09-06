# -*- coding: utf-8 -*-
"""2018 이음새 보정계수 — 2005~2017 원주가를 2018~ 수정주가 기준에 맞춘다.

발견(2026-09-06 감사): 2005~2017 KRX 백필은 원주가, 2018~ 는 수정주가(나중 분할이 소급 반영).
그래서 2018-01-02 에 코스피 199 · 코스닥 398 종목이 점프한다. 아모레퍼시픽 2015 분할이
-90% 폭락으로 남아 있고, 이음새 비율의 40~57% 는 정수 분할비가 아니라(무상증자가 섞여) 비율만으로는
못 맞춘다. 네이버(FDR) 수정주가의 2017-12-28 종가 ÷ 우리 원주가 = 보정계수. 폐지 종목은 이음새
점프에 0% 라 받을 필요가 없다(대신 build_panel 에서 주식수 비율로 분할을 따로 보정한다).
산출: data/seam_factor.csv (ticker, factor, raw, adj)
사용: python seam_factor.py
"""
import io, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import pandas as pd, numpy as np
import FinanceDataReader as fdr
from pathlib import Path
BASE = Path(__file__).parent
OUT = BASE/"data"/"seam_factor.csv"
done = pd.read_csv(OUT, dtype={"ticker": str}).set_index("ticker") if OUT.exists() else pd.DataFrame(columns=["factor","raw","adj"])
rows = {t: r for t, r in done.iterrows()}
todo = []
for f in ("panel_kp.pkl", "panel_kq.pkl"):
    K = pd.read_pickle(BASE/"data"/f)[["ticker","date","close","grp"]]
    a = K[K.date=="20171228"].set_index("ticker"); b = K[K.date=="20180102"].set_index("ticker")
    r = (a.close / b.close).dropna()
    # 이음새에서 ±15% 넘게 튀는 상장 종목 전부(정수비 아닌 무상증자 섞임까지)
    J = r[((r>1.15)|(r<0.87)) & (a.loc[r.index].grp=="생존")]
    todo += [(t, a.loc[t].close) for t in J.index if t not in rows]
print(f"이음새 후보 {len(todo)}종목 (이미 {len(rows)}개 있음)")
ok = fail = 0; t0 = time.time()
for i, (t, raw) in enumerate(todo, 1):
    try:
        f = fdr.DataReader(t, "2017-12-20", "2017-12-29")["Close"]
        adj = float(f.iloc[-1]) if len(f) else np.nan
    except Exception: adj = np.nan
    if adj == adj and adj > 0: rows[t] = pd.Series(dict(factor=adj/raw, raw=raw, adj=adj)); ok += 1
    else: fail += 1
    if i % 100 == 0:
        print(f"  {i}/{len(todo)} · 성공 {ok} · 실패 {fail} · {(time.time()-t0)/60:.1f}분", flush=True)
        pd.DataFrame(rows).T.rename_axis("ticker").to_csv(OUT)
    time.sleep(0.15)
R = pd.DataFrame(rows).T.rename_axis("ticker"); R.to_csv(OUT)
print(f"완료 · 성공 {ok} · 실패 {fail} · 저장 {len(R)}종목 · {(time.time()-t0)/60:.1f}분")
if len(R):
    R["factor"] = R.factor.astype(float)
    print("  계수 분포: 중앙", round(R.factor.median(),3), "· ≤0.25(5분할 이상)", int((R.factor<=0.25).sum()), "· 0.25~0.8", int(((R.factor>0.25)&(R.factor<0.8)).sum()), "· 0.8~1.25(거의 1)", int(((R.factor>=0.8)&(R.factor<=1.25)).sum()), "· >1.25(병합)", int((R.factor>1.25).sum()))
