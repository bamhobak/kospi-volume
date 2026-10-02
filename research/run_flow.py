# -*- coding: utf-8 -*-
"""수급 급증 재료를 붙여 run_spec 을 돌린다 (2026-10-02 사용자 제안: 외국인 1일 매수·개인 1일 매도가 직전 5일의 3·5배).

data/investor.db flow11(투자자별 하루 순매수 금액, 2018-01~) → 패널에 열 추가:
  fnet  외국인 순매수(원)          fx = fnet ÷ 직전 5거래일 |외국인 순매수| 평균   famt = fnet ÷ 20일 평균 거래대금 × 100(%)
  inet  개인 순매수(원)            ix = (-inet) ÷ 직전 5거래일 |개인 순매수| 평균  iamt = (-inet) ÷ 20일 평균 거래대금 × 100(%)
수급은 장 마감 뒤 확정 → 신호일 값으로 다음날 시가에 산다(미래 없음). 2018 이전은 자료가 없어 홀드아웃(05~15)은 비고 학습은 2018~22.

    python research/run_flow.py research/specs/H0277.json ...
"""
import sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
import run_extra as RX
import run_spec as R

_orig_add = RX.add_cols


def add_cols(A, mk):
    A = _orig_add(A, mk)
    if mk != "KR":
        return A
    c = sqlite3.connect("file:" + str(BASE / "data" / "investor.db") + "?mode=ro", uri=True)
    F = pd.read_sql("SELECT ticker, date, indiv, frgn FROM flow11", c).sort_values(["ticker", "date"])
    g = F.groupby("ticker", sort=False)
    bf = g.frgn.transform(lambda s: s.abs().shift(1).rolling(5, min_periods=5).mean())
    bi = g.indiv.transform(lambda s: s.abs().shift(1).rolling(5, min_periods=5).mean())
    F["fnet"] = F.frgn; F["inet"] = F.indiv
    F["fx"] = F.frgn / bf.replace(0, np.nan)
    F["ix"] = (-F.indiv) / bi.replace(0, np.nan)
    A.drop(columns=[x for x in ("fnet", "inet", "fx", "ix", "famt", "iamt") if x in A.columns], inplace=True)
    m = A[["ticker", "date", "amt20"]].merge(F[["ticker", "date", "fnet", "inet", "fx", "ix"]], on=["ticker", "date"], how="left")
    for col in ("fnet", "inet", "fx", "ix"):
        A[col] = m[col].values
    amt = m.amt20.values * 1e8
    with np.errstate(all="ignore"):
        A["famt"] = A.fnet / amt * 100
        A["iamt"] = (-A.inet) / amt * 100
    return A


RX.add_cols = add_cols

if __name__ == "__main__":
    sys.exit(RX.main(sys.argv[1:]))
