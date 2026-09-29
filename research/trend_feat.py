# -*- coding: utf-8 -*-
"""네이버 검색량 → 관심도 재료 (2026-09-29, 사용자 제안 1번 '관심 없는 매집').

data/naver_trend.db(collect_naver_trend.py · 종목명 일별 검색량 · 종목마다 자기 최대 = 100 인 상대값)에서
  att    최근 28일(달력) 평균 ÷ 그 앞 365일 평균 — 1보다 작을수록 관심이 식었다(자기 과거 대비라 스케일 무관)
  att7   최근 7일 평균 ÷ 앞 365일 평균 — 짧은 관심 급증/급랭
  zfrac  앞 365일 중 검색량 0 인 날 비율 — 원래 아무도 안 찾는 종목(비율이 의미 없음)을 거르는 데 쓴다
미래 없음: d 날짜 값은 d 까지의 검색량만 쓴다(검색량은 그날 밤 확정 → 다음날 시가 매수 전).
→ research/cache/naver_att.pkl (ticker, date, att, att7, zfrac) · 거래일만 남긴다(kr_scan 날짜).

    python research/trend_feat.py
"""
import sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent


def main():
    t0 = time.time()
    c = sqlite3.connect(BASE / "data" / "naver_trend.db")
    T = pd.read_sql("SELECT ticker, date, ratio FROM trend", c)
    T = T.sort_values(["ticker", "date"]).reset_index(drop=True)
    g = T.groupby("ticker", sort=False).ratio
    s28 = g.transform(lambda s: s.rolling(28, min_periods=20).mean())
    s7 = g.transform(lambda s: s.rolling(7, min_periods=5).mean())
    base = g.transform(lambda s: s.shift(28).rolling(365, min_periods=300).mean())
    z = (T.ratio <= 0).astype(float).groupby(T.ticker, sort=False).transform(lambda s: s.shift(28).rolling(365, min_periods=300).mean())
    T["att"] = s28 / base.replace(0, np.nan)
    T["att7"] = s7 / base.replace(0, np.nan)
    T["zfrac"] = z

    out = T.dropna(subset=["att"])[["ticker", "date", "att", "att7", "zfrac"]]
    out.to_pickle(ROOT / "cache" / "naver_att.pkl")
    print("관심도 %s행 · %d종목 · %s~%s · %.0f초" % (f"{len(out):,}", out.ticker.nunique(), out.date.min(), out.date.max(), time.time() - t0))
    print(out.att.describe().round(3).to_string())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
