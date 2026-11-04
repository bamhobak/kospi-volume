# -*- coding: utf-8 -*-
"""1년 1억 시뮬레이션용 자료(2026-11-05 사용자 "작년 이맘때 1억 — 1년 굴려 봐") — 연구 패널(kr_scan, 2026-08-28 까지)에
그 뒤 일봉(FinanceDataReader, 08-24~ 겹쳐 받아 이음 확인)을 붙여 data/y1_kr.pkl 로. 겹치는 날 종가가 1% 넘게 다르면
(액면분할 등으로 과거가 다시 맞춰짐) 그 종목은 처음부터 다시 받는다. 시총은 마지막 패널 시총 × 종가 비율로 잇는다.
    python research/y1_data.py
"""
import sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
BASE = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import FinanceDataReader as fdr

COLS = ["ticker", "date", "open", "high", "low", "close", "volume", "pref", "marcap", "mk"]


def get(t, start):
    for att in range(3):
        try:
            X = fdr.DataReader(t, start)
            if X is None or not len(X): return None
            X = X.reset_index(); X["date"] = X.iloc[:, 0].dt.strftime("%Y%m%d")
            return X.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})[["date", "open", "high", "low", "close", "volume"]]
        except Exception:
            time.sleep(2 * (att + 1))
    return None


def main():
    A = pd.read_pickle(BASE / "data" / "kr_scan.pkl")[COLS]
    A = A.drop_duplicates(["ticker", "date"], keep="last")
    last = A.date.max()
    act = A[A.date >= "20260801"].ticker.unique()
    print("패널 %s줄 · 마지막 %s · 이어 받을 종목 %d" % (f"{len(A):,}", last, len(act)), flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(4) as ex:
        R = dict(zip(act, ex.map(lambda t: get(t, "2026-08-24"), act)))
    print("받기 %.1f분 · 실패 %d" % ((time.time() - t0) / 60, sum(v is None for v in R.values())), flush=True)
    new, redo = [], []
    G = {t: g for t, g in A[A.date >= "20260824"].groupby("ticker")}
    for t, X in R.items():
        if X is None: continue
        o = G.get(t)
        if o is not None:
            m = o.merge(X, on="date", suffixes=("", "_n"))
            if len(m) and ((m.close_n / m.close - 1).abs() > 0.01).any(): redo.append(t); continue
        new.append(X[X.date > last].assign(ticker=t))
    print("이음 어긋남(다시 받기) %d종목" % len(redo), flush=True)
    for t in redo:                                                       # 과거가 다시 맞춰진 종목 — 전체를 새로 받아 바꾼다
        X = get(t, "2009-01-01")
        if X is None: continue
        old = A[A.ticker == t].set_index("date")
        X = X.assign(ticker=t)
        X["pref"] = bool(old.pref.iloc[-1]); X["mk"] = old.mk.iloc[-1]
        X["marcap"] = X.date.map(old.marcap)
        A = pd.concat([A[A.ticker != t], X[COLS]])
    N = pd.concat(new) if new else pd.DataFrame(columns=COLS)
    info = A.sort_values("date").groupby("ticker").tail(1).set_index("ticker")
    N["pref"] = N.ticker.map(info.pref).fillna(False); N["mk"] = N.ticker.map(info.mk)
    lc, lm = info.close, info.marcap
    N["marcap"] = N.ticker.map(lm) * N.close / N.ticker.map(lc)
    A = pd.concat([A, N[COLS]]).sort_values(["ticker", "date"]).drop_duplicates(["ticker", "date"], keep="last").reset_index(drop=True)
    A.to_pickle(BASE / "data" / "y1_kr.pkl")
    print("저장 %s줄 · %s~%s · 새 날짜 %s" % (f"{len(A):,}", A.date.min(), A.date.max(), sorted(N.date.unique())[:3] + ["…"] + sorted(N.date.unique())[-2:]))


if __name__ == "__main__":
    main()
