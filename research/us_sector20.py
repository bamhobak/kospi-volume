# -*- coding: utf-8 -*-
"""미장 업종 20일 수익 중앙값(날짜별) → 국내 업종 짝 → research/cache/us_sec20.pkl (2026-09-29, 제안 목록 3번 준비).

미장 date d 의 값은 **다음 국내 거래일**에 쓴다(미장 마감 = 한국 새벽). 5일 늦춘 값(us20_l5)도 만든다 —
다음날 아침 시초가에 이미 반영된 부분이 아니라 **5일 이상 지난 뒤에도 남는 흐름**만 보려는 것.
짝(미장 Industry → 국내 up)은 넓은 대응이다 — 결과를 보기 전에 고정.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
PAIR = {"반도체": "전기전자", "생명 공학 및 의학 연구": "제약", "제약": "제약",
        "항공우주 및 방위": "운송장비·부품", "자동차 및 트럭 제조": "운송장비·부품", "자동차, 트럭 및 오토바이 부품": "운송장비·부품",
        "오일, 가스 정제 및 마케팅": "화학", "상품 화학": "화학", "철 및 강철": "금속", "특수 채굴 및 금속": "금속",
        "은행": "금융", "소프트웨어": "소프트웨어 개발 및 공급업", "IT 서비스 및 컨설팅": "소프트웨어 개발 및 공급업",
        "해양 화물 및 물류": "운송·창고", "의료 장비, 물품 및 유통": "의료·정밀기기", "첨단 의료 장비 및 기술": "의료·정밀기기",
        "건설 및 엔지니어링": "건설", "식품 가공": "음식료·담배"}


def main():
    A = pd.read_pickle(BASE / "data/us_scan.pkl")
    A = A[((~A.pref.fillna(False)) & (A.rawclose >= 3)).fillna(False)][["ticker", "date", "ret20", "amt20"]]
    T = pd.read_csv(BASE / "data/us/tickers.csv", dtype=str)[["Symbol", "Industry"]]
    A = A.merge(T, left_on="ticker", right_on="Symbol", how="inner")
    A = A[A.Industry.isin(PAIR)]
    A = A[A.amt20.groupby(A.date).rank(pct=True) >= 0.3]            # 아주 얇은 종목은 뺀다
    A["kup"] = A.Industry.map(PAIR)
    M = A.groupby(["date", "kup"]).ret20.agg(["median", "size"]).reset_index()
    M = M[M["size"] >= 5].rename(columns={"median": "us20", "kup": "up"})
    M = M.sort_values(["up", "date"])
    M["us20_l5"] = M.groupby("up").us20.shift(5)
    M.to_pickle(ROOT / "cache" / "us_sec20.pkl")
    print(len(M), M.date.min(), M.date.max(), M.up.nunique())


if __name__ == "__main__":
    main()
