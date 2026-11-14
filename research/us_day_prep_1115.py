# -*- coding: utf-8 -*-
"""2026-11-15 사용자 "응 둘 다 해줘" — 미장 데이 후보 두 개의 밤 받기 목록(종목·미국 거래일) 만들기.
  A [미장 장전 얇은 갭하락]: 소형주(20일 평균 거래대금 $0.5M~$30M · 종가 $1↑)가 개장 갭 ≤ -2% 로 연 날 → 그날 06:41~10:00 ET 1분봉(장전 + 개장 30분)
     개장 갭으로 고르는 건 '시가에 사는' 규칙이라 미래 정보 아님(시가가 나온 순간 앎).
  B [주간거래 낙폭]: 그날 20일 평균 거래대금 상위 1,000(한국 개인이 많이 하는 큰 종목들) → 그 미국 거래일 앞 밤 주간거래(00:41~04:00 ET) 1분봉
     값이 움직였는지는 받아 봐야 알므로 고르지 않고 전부 — 밤 받기가 날짜를 무작위 순서로 받으니 덜 받아도 고른 표본.
기간 2022-06-01 ~ 패널 끝(us_full_2007). 결과 research/cache/us_gap_pairs.parquet · us_on_pairs.parquet (t, d)."""
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).resolve().parent.parent
U = pd.read_pickle(BASE / "data" / "us_full_2007.pkl")[["ticker", "date", "rawclose", "px", "buy", "amt20"]]
U = U[U.date >= "20220501"].sort_values(["ticker", "date"]).reset_index(drop=True)
g = U.groupby("ticker", sort=False)
U["d1"] = g.date.shift(-1)
U["gap1"] = (U.buy / U.px - 1) * 100                                     # 다음 날 개장 갭(조정 가격끼리)
A = U[(U.amt20 >= 0.5) & (U.amt20 <= 30) & (U.rawclose >= 1) & (U.gap1 <= -2) & (U.gap1 > -60) & U.d1.notna()]
A = A[A.d1 >= "20220601"][["ticker", "d1"]].rename(columns={"ticker": "t", "d1": "d"}).drop_duplicates()
A.to_parquet(BASE / "research" / "cache" / "us_gap_pairs.parquet", index=False)
B = U[U.date >= "20230201"].copy()                                    # 토스 주간거래 봉은 2023-02 부터(11-15 확인)
B["rk"] = B.groupby("date").amt20.rank(ascending=False, method="first")
B = B[B.rk <= 1000][["ticker", "date"]].rename(columns={"ticker": "t", "date": "d"}).drop_duplicates()
B.to_parquet(BASE / "research" / "cache" / "us_on_pairs.parquet", index=False)
print("A 갭하락 소형주 %d쌍 · %d날 · 하루 중앙 %.0f · 종목 %d" % (len(A), A.d.nunique(), A.groupby("d").size().median(), A.t.nunique()))
print("B 주간거래 대상 %d쌍 · %d날 · 종목 %d" % (len(B), B.d.nunique(), B.t.nunique()))
