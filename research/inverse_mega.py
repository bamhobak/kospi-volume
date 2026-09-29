# -*- coding: utf-8 -*-
"""단일종목 인버스(토스에서 살 수 있는 미국 대형주 -1배 상품)로 '나쁜 신호' 를 공매도처럼 쓸 수 있나 (2026-09-30 사용자 질문).

인버스로 벌려면 '시장보다 덜 오른다' 가 아니라 **그 종목이 절대적으로 떨어져야** 한다.
대상 = 단일종목 인버스가 상장된 대형주(1배 환산). 그 종목들에서 흔히 '나쁘다' 고 하는 자리 여럿의
이후 20·60일 **절대 수익** 중앙·음수 비율을 본다. 인버스 비용(보수 ~1%/년 + 일일 재조정 손실)은 빼기 전이다.

    python research/inverse_mega.py
"""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
MEGA = "TSLA NVDA AAPL AMZN MSFT GOOGL META AMD NFLX COIN PLTR MSTR AVGO SMCI MU INTC BA LLY UNH JPM BABA".split()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    A = pd.read_pickle(BASE / "data" / "us_scan.pkl")
    A = A[A.ticker.isin(MEGA) & (A.date >= "20160101")].copy()
    A["vol_d"] = A.groupby("ticker").volume.transform(lambda s: s / s.rolling(20).mean())
    C = {
        "전체(기준선)": A.index == A.index,
        "20일 +30% 넘게 급등": A.ret20 >= 30,
        "250일 +150% 넘게 급등": A.ret250 >= 150,
        "20일선 +15% 이격": A.dma20 >= 15,
        "60일선 아래로 이탈(-5%)": A.dma60 <= -5,
        "120일선 -15% 아래(하락 추세)": A.dma120 <= -15,
        "고점 대비 -30% 이하": A.fromhi <= -30,
        "하루 거래량 3배 + 하락(gap<0)": (A.vm1 >= 3) & (A.gap < 0),
    }
    O = ["# 단일종목 인버스 대상 대형주 — '나쁜 자리' 뒤 절대 수익 · %s" % time.strftime("%Y-%m-%d"), "",
         "대상 %d종목 · 2016~ · 인버스 비용 빼기 전(인버스 수익 ≈ −주식 수익 − 보수·재조정 손실)" % A.ticker.nunique(), "",
         "| 자리 | 표본 | 20일 중앙 | 20일 하락 비율 | 60일 중앙 | 60일 하락 비율 | 60일 하락 해 |", "|---|---|---|---|---|---|---|"]
    for k, m in C.items():
        z = A[m]
        z60 = z.dropna(subset=["n60"])
        ys = z60.groupby(z60.date.str[:4]).n60.median()
        O.append("| %s | %s | %+.2f | %.0f%% | %+.2f | %.0f%% | %d/%d |" % (
            k, f"{len(z):,}", z.n20.median(), (z.n20 < 0).mean() * 100, z60.n60.median(), (z60.n60 < 0).mean() * 100,
            (ys < 0).sum(), len(ys)))
    O += ["", "하락 비율이 50%를 넘고 중앙이 음수여야 인버스가 이긴다(그 뒤 보수·재조정 손실도 넘어야 한다)."]
    (ROOT / "reports" / ("inverse_mega_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(O) + "\n", encoding="utf-8")
    print("\n".join(O))


if __name__ == "__main__":
    main()
