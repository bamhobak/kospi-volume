# -*- coding: utf-8 -*-
"""Mind Math Money 'MASTER AI Trading in 70 Minutes'(54i7wfbuCQA · 2026-10-15 사용자 링크) 실측 — H0338.

영상 안 유일한 백테스트: 비트코인 일봉 '종가가 50일 단순이평 위로 마감 → 매수, 아래로 마감 → 매도(현금)'.
주장: 2015-05~ 수수료 넣어도 보유의 1.8배 — 수익이 아니라 -83% 하락장을 피해서.
여기선 그 규칙을 비트코인·코스피·코스닥·S&P500·나스닥에 그대로, 이웃 기간(20·30·50·100·150·200일)과 나란히.
매매: 신호 난 날 종가에 판정 → 다음날 시가가 없는 지수는 다음날 종가 수익부터 반영(하루 늦게) · 비용 한 번 바꿀 때마다 0.1%.
잣대: 연복리·최대 낙폭·보유 대비 배수 · 구간 옛날 ~2015 · 학습 2016~22 · 검증 2023~ (각 구간 따로 처음부터).
    python research/yt_sma_timing.py
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
ASSETS = [("비트코인", "BTC/USD", "2014-09-01"), ("코스피", "KS11", "2000-01-01"), ("코스닥", "KQ11", "2000-01-01"),
          ("S&P500", "US500", "2000-01-01"), ("나스닥", "IXIC", "2000-01-01")]
NS = [20, 30, 50, 100, 150, 200]
COST = 0.1
PER = [("옛날", "2000-01-01", "2015-12-31"), ("학습", "2016-01-01", "2022-12-31"), ("검증", "2023-01-01", "2099-12-31")]


def stats(r):
    eq = (1 + r).cumprod()
    yrs = len(r) / 252
    return eq.iloc[-1], eq.iloc[-1] ** (1 / yrs) - 1 if yrs > 0 else np.nan, (eq / eq.cummax() - 1).min()


def main():
    for nm, code, since in ASSETS:
        try: X = fdr.DataReader(code, since)
        except Exception as ex: P("%s 받기 실패 %s" % (nm, ex)); continue
        c = X["Close"].astype(float); c = c[c > 0]
        r = c.pct_change().fillna(0)
        P("\n## %s (%s~%s)" % (nm, c.index[0].date(), c.index[-1].date()))
        P("| 판 | %s |" % " | ".join("%s 연복리·낙폭" % p for p, _, _ in PER)); P("|---|---|---|---|")
        rows = {"보유": r}
        for n in NS:
            ma = c.rolling(n).mean()
            pos = (c > ma).astype(float).shift(1).fillna(0)          # 오늘 종가로 판정 → 다음날 수익부터
            sw = pos.diff().abs().fillna(0)
            rows["%d일선" % n] = pos * r - sw * COST / 100
        for k, rr in rows.items():
            cs = []
            for p, a, b in PER:
                s = rr[(rr.index >= a) & (rr.index <= b)]
                if len(s) < 200: cs.append("-"); continue
                m, cg, dd = stats(s)
                bh = stats(r[(r.index >= a) & (r.index <= b)])[0]
                cs.append("%+.1f%% · %.0f%% (보유의 %.2f배)" % (cg * 100, dd * 100, m / bh))
            P("| %s | %s |" % (k, " | ".join(cs)))
        if nm == "비트코인":
            s = rows["50일선"][rows["50일선"].index >= "2015-05-01"]; b = r[r.index >= "2015-05-01"]
            P("\n영상 구간 그대로(2015-05~): 50일선 %.0f배 · 보유 %.0f배 → 보유의 %.2f배 · 낙폭 %.0f%% vs %.0f%%" % (
                stats(s)[0], stats(b)[0], stats(s)[0] / stats(b)[0], stats(s)[2] * 100, stats(b)[2] * 100))
    (Path(__file__).resolve().parent / "cache" / "yt_sma_timing.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
