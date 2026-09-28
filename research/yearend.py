# -*- coding: utf-8 -*-
"""**연말 양도세 매도 → 1월 반등** (2026-09-29, 사용자 제안 목록 7번).

12월엔 대주주 요건을 피하려는 개인의 기계적 매도가 몰린다 → 그 물량이 빠진 종목이 1월 초 되돌아온다.
1년에 한 번 나는 신호라 run_spec(월 CI 12개월↑ 필요)으로는 판정이 안 된다 — **연도별 표**로 잰다.

  신호일 = 12월 마지막 거래일 · 유니버스 = 그날 거래대금 상위 40%(run_spec 과 같다)
  G1 연초 대비 -20% 이하(양도세 손실 확정 후보) · G2 G1 + 12월 개인 순매도 ÷ 거래대금 ≤ -5%(2018~, 개인 자료 시작)
  G3 연초 대비 -30% 이하 · G4 G1 + 12월 개인 순매도 < 0
  수익: 다음날(1월 첫날) 시가 매수 → 10·20거래일 뒤 종가(n10·n20, 비용 차감) · 비교 = 같은 날 유니버스 나머지 종목 중앙
  대주주 기준: 2023-12 에 10억→50억 완화(12월 매도 압력 약해짐) — 2023~ 를 따로 본다.
  보류 중인 H0026(연말 3거래일, 전체 종목)의 '이유 있는 종목만' 개선판이다.

    python research/yearend.py
"""
import sqlite3, sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
import run_spec as R
from verdict import log_trials


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    A, uni, since = R.load_market("KR")
    A["uni"] = uni.values
    yr = A.date.str[:4]
    A["ytd"] = (A.close / A.groupby([A.ticker, yr]).close.transform("first") - 1) * 100
    dec = A.date[A.date.str[4:6] == "12"]
    last = set(dec.groupby(dec.str[:4]).max().values)
    # 12월 개인 순매수 합 ÷ 12월 거래대금 합(%)
    c = sqlite3.connect(BASE / "data" / "investor.db")
    F = pd.read_sql("select ticker, date, indiv from flow where substr(date,5,2)='12'", c)
    F["y"] = F.date.str[:4]
    Dm = A[A.date.str[4:6] == "12"].assign(v=lambda x: x.close * x.volume, y=lambda x: x.date.str[:4])
    V = Dm.groupby(["ticker", "y"]).v.sum()
    I = F.groupby(["ticker", "y"]).indiv.sum()
    Q = (I / V.reindex(I.index) * 100).rename("decind")
    X = A[A.date.isin(last) & A.uni].copy()
    X["y"] = X.date.str[:4]
    X = X.join(Q, on=["ticker", "y"])
    G = {"G1 연초 대비 -20%↓": X.ytd <= -20, "G2 G1 + 12월 개인 순매도 ≤ -5%": (X.ytd <= -20) & (X.decind <= -5),
         "G3 연초 대비 -30%↓": X.ytd <= -30, "G4 G1 + 12월 개인 순매도 < 0": (X.ytd <= -20) & (X.decind < 0)}
    O = ["# 연말 양도세 매도 → 1월 반등 · 국내 · %s" % time.strftime("%Y-%m-%d"), "",
         "12월 마지막 거래일 신호 · 1월 첫날 시가 매수 · 비용 차감. 차이 = 그룹 중앙 − 같은 날 유니버스 나머지 중앙(%p).", ""]
    for h in (10, 20):
        col = "n%d" % h
        O += ["## %d거래일 보유" % h, "", "| 해(신호) | " + " | ".join(G) + " | 나머지 중앙 |", "|---|" + "---|" * (len(G) + 1)]
        diffs = {k: {} for k in G}
        for y in sorted(X.y.unique()):
            z = X[X.y == y]
            if z[col].notna().sum() < 30:
                continue
            cells = []
            for k, m in G.items():
                g, rest = z[m][col].dropna(), z[~m][col].dropna()
                if len(g) >= 5:
                    diffs[k][y] = g.median() - rest.median()
                    cells.append("%+.1f (n%d)" % (diffs[k][y], len(g)))
                else:
                    cells.append("-")
            O.append("| %s | %s | %+.1f%% |" % (y, " | ".join(cells), z[col].median()))
        O += ["", "| 그룹 | 해 수 | 평균 차이 | 양수 해 | t | 2005~15 평균 | 2016~22 평균 | 2023~ 평균(대주주 완화 뒤) |", "|---|---|---|---|---|---|---|---|"]
        for k, dmap in diffs.items():
            v = pd.Series(dmap)
            if len(v) < 3:
                continue
            t = v.mean() / (v.std(ddof=1) / np.sqrt(len(v))) if len(v) > 1 and v.std() > 0 else np.nan
            seg = lambda lo, hi: v[(v.index >= lo) & (v.index <= hi)].mean()
            O.append("| %s | %d | %+.2f | %d/%d | %.2f | %+.2f | %+.2f | %+.2f |" % (
                k, len(v), v.mean(), (v > 0).sum(), len(v), t, seg("2005", "2015"), seg("2016", "2022"), seg("2023", "2099")))
        O.append("")
    log_trials("yearend_%s" % time.strftime("%Y%m%d"), 8)
    rp = ROOT / "reports" / ("yearend_%s.md" % time.strftime("%Y%m%d"))
    rp.write_text("\n".join(O) + "\n", encoding="utf-8")
    print("\n".join(O))


if __name__ == "__main__":
    main()
