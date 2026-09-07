# -*- coding: utf-8 -*-
"""자사주 조건을 얹으면 코스닥 신호가 얼마나 줄어드나 — 조이기 전에 대가부터 센다.

사용자 지적(2026-09-07): "코스닥 월건은 지금도 별로 없어서 더 조이면 안될듯해".
맞는 말인지 숫자로 확인한다. 문턱을 얹기 전에 '신호가 몇 건에서 몇 건이 되는지' 와
'신호 난 달 수가 얼마나 줄어드는지' 를 먼저 본다. 성적이 좋아져도 자리가 비면 계좌는 손해다.
"""
import io, os, sys, sqlite3, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KQ, KB, RULES = ns["KQ"], ns["KB"], ns["RULES"]
c = sqlite3.connect("file:data/dart/shares.db?mode=ro", uri=True)
SH = pd.read_sql("SELECT stock_code ticker, year, issued, treasury FROM shares", c); c.close()
SH = SH[(SH.issued > 0) & SH.treasury.notna()]
SH["trs"] = SH.treasury / SH.issued * 100
SH["year"] = SH.year.astype(str)
SH = SH.groupby(["ticker","year"], as_index=False).trs.max()
for K in (KQ, KB):
    K["_y"] = (K.date.str[:4].astype(int) - 1).astype(str)
    K["trs"] = K.merge(SH.rename(columns={"year":"_y"}), on=["ticker","_y"], how="left").trs.values
def dedup(X, hold, K):
    di = {x:i for i,x in enumerate(sorted(K.date.unique()))}
    X = X.assign(_di=X.date.map(di)).sort_values("_di"); keep, last = [], {}
    for t,i,ix in zip(X.ticker.values, X._di.values, X.index):
        if last.get(t,-10**9) >= i: continue
        last[t] = i+hold; keep.append(ix)
    return X.loc[keep]
print("자사주 조건을 얹었을 때 잃는 것 (2016~2026, 실거래 기준)")
print(f"  {'규칙':<14}{'조건':<16}{'신호':>6}{'신호난달':>9}{'자료없음':>9}{'평균':>8}{'중앙':>8}{'승률':>6}")
for rid, nm in (("D1","낙폭과대"), ("D2","저PBR 낙폭"), ("P5","자사주 낙폭")):
    K, hold, stop, pct, mx, cond = RULES[rid]
    col = f"n{hold}"
    base = dedup(K[cond.fillna(False)].copy(), hold, K)
    base = base[(base.date >= "20160101")].dropna(subset=[col])
    span = len(set(pd.date_range("2016-01-01","2026-09-01",freq="MS").strftime("%Y%m")))
    for lab, sub in (("현행(조건 없음)", base),
                     ("+ 자사주 ≥1%", base[base.trs >= 1]),
                     ("+ 자사주 ≥3%", base[base.trs >= 3]),
                     ("+ 자사주 ≥5%", base[base.trs >= 5]),
                     ("+ 자사주 결측도 통과 ≥3%", base[base.trs.isna() | (base.trs >= 3)])):
        if not len(sub): print(f"  {nm:<14}{lab:<16}{'0':>6}"); continue
        na = base.trs.isna().mean()*100
        print(f"  {nm:<14}{lab:<16}{len(sub):>6}{sub.date.str[:6].nunique():>7}개월{na:>8.0f}%"
              f"{sub[col].mean():>+7.1f}%{sub[col].median():>+7.1f}%{(sub[col]>0).mean()*100:>5.0f}%")
    print()
