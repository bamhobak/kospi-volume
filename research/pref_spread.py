# -*- coding: utf-8 -*-
"""**우선주 괴리 회귀** (2026-09-29, 사용자 제안 목록 5번 — 규칙판에 없는 유일한 시장 중립 축).

우선주/보통주 가격 비율이 자기 1년 분포 하위 10% 아래로 처음 내려가면(우선주가 지나치게 싸지면) → 우선주 매수 60일.
  · 짝: 우선주 코드 앞 5자리 + '0' = 보통주(국내 관행). 둘 다 그날 시세가 있어야 한다.
  · 비율 문턱 = 직전 250거래일 비율의 10% 분위(오늘 제외) · 처음 들어온 날만(보유 중 재신호 무시)
  · 수익: 우선주 n20·n60(다음날 시가 매수 · 비용 차감) · **짝 수익** = 우선주 − 보통주(같은 구간) — 시장 방향을 뺀 순수 괴리 회귀
  · 유동성: 우선주는 거래대금이 작다 — 20일 평균 거래대금 3억·10억 이상으로 따로 본다(3억 계좌 시장충격)
  · 비교: 같은 날 우선주 전체의 같은 구간 중앙(우선주 자체의 흐름)
판정 잣대(미리 정함): 학습 16~22·검증 23~ 중앙 둘 다 양수 · 짝 수익 중앙도 양수 · 양수 해 60%↑ · 상위 5% 뺀 평균 양수.

    python research/pref_spread.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
from verdict import log_trials, boot_ci


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    A = pd.read_pickle(BASE / "data/kr_scan.pkl")[["ticker", "date", "close", "buy", "amt20", "cost", "n20", "n60", "pref"]]
    A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
    Pf = A[A.pref.fillna(False)].copy()
    Pf["common"] = Pf.ticker.str[:5] + "0"
    Cm = A[~A.pref.fillna(False)][["ticker", "date", "close", "n20", "n60"]].rename(
        columns={"ticker": "common", "close": "cclose", "n20": "cn20", "n60": "cn60"})
    Z = Pf.merge(Cm, on=["common", "date"], how="inner").sort_values(["ticker", "date"]).reset_index(drop=True)
    Z["ratio"] = Z.close / Z.cclose
    g = Z.groupby("ticker", sort=False)
    Z["q10"] = g.ratio.transform(lambda s: s.shift(1).rolling(250, min_periods=200).quantile(0.10))
    Z["q50"] = g.ratio.transform(lambda s: s.shift(1).rolling(250, min_periods=200).median())
    below = (Z.ratio <= Z.q10)
    Z["new"] = below & ~below.groupby(Z.ticker).shift(1).fillna(False).astype(bool)
    O = ["# 우선주 괴리 회귀 · 국내 · %s" % time.strftime("%Y-%m-%d"), "",
         "우선주 %d종목(보통주 짝 있는 것) · 비율 = 우선주 ÷ 보통주 종가. 짝 수익 = 우선주 − 보통주(같은 구간, 둘 다 비용 차감)." % Z.ticker.nunique(), ""]
    ben = {h: Z.dropna(subset=["n%d" % h]).groupby("date")["n%d" % h].median() for h in (20, 60)}
    cells = 0
    for liq in (0, 3, 10):
        for h in (20, 60):
            X = Z[Z.new & (Z.amt20 >= liq) & (Z.buy > 0)].dropna(subset=["n%d" % h, "cn%d" % h]).copy()
            keep, last = [], {}
            di = {d: i for i, d in enumerate(sorted(Z.date.unique()))}
            for t, d_, ix in zip(X.ticker.values, X.date.values, X.index):
                i = di[d_]
                if last.get(t, -10 ** 9) >= i:
                    continue
                last[t] = i + h; keep.append(ix)
            X = X.loc[keep]
            X["r"] = X["n%d" % h]; X["sp"] = X["n%d" % h] - X["cn%d" % h]; X["bm"] = X.date.map(ben[h])
            cells += 1
            O += ["## 거래대금 %s · %d일" % ("제한 없음" if liq == 0 else "%d억↑" % liq, h), "",
                  "| 구간 | n | 우선주 중앙 | 절삭 | 승률 | **짝 수익 중앙** | 짝 승률 | 같은 날 우선주 전체 중앙 | 월CI(짝) | 양수 해(짝 중앙) |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
            for lbl, lo, hi in (("홀드아웃 05~15", "20050101", "20151231"), ("학습 16~22", "20160101", "20221231"),
                                ("검증 23~", "20230101", "20991231"), ("전체 16~", "20160101", "20991231")):
                z = X[(X.date >= lo) & (X.date <= hi)]
                if len(z) < 20:
                    O.append("| %s | %d | 표본 부족 | | | | | | | |" % (lbl, len(z))); continue
                ym = z.groupby(z.date.str[:6]).sp.mean(); ys = z.groupby(z.date.str[:4]).sp.median()
                O.append("| %s | %s | %+.2f | %+.2f | %.0f%% | **%+.2f** | %.0f%% | %+.2f | %s | %d/%d |" % (
                    lbl, f"{len(z):,}", z.r.median(), z.r[z.r <= z.r.quantile(0.95)].mean(), (z.r > 0).mean() * 100,
                    z.sp.median(), (z.sp > 0).mean() * 100, z.bm.median(),
                    ("%+.2f" % boot_ci(ym)) if len(ym) >= 12 else "-", (ys > 0).sum(), len(ys)))
            O.append("")
    log_trials("pref_spread_%s" % time.strftime("%Y%m%d"), cells)
    rp = ROOT / "reports" / ("pref_spread_%s.md" % time.strftime("%Y%m%d"))
    rp.write_text("\n".join(O) + "\n", encoding="utf-8")
    print("\n".join(O))


if __name__ == "__main__":
    main()
