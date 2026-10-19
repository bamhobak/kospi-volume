# -*- coding: utf-8 -*-
"""미장 [실적 서프라이즈](N6) 상세 분석 (2026-10-19 사용자).
사이트 정의 그대로 다시 만든다: 그날 발표분 서프라이즈 상위 30% · 발표 다음 거래일 +3%↑ · 거래대금 상위 40% · 주가 $3↑ ·
60거래일 전 대비 -20%↓ 빠졌다가 하락분 1/4↑ 회복(아직 60일 전 가격 아래) → 다음날 시가 매수 · 60거래일 보유 · 같은 종목 보유 중 재신호 없음.
자료: 실적 data/us/analyst/earn_*.pkl(살아남은 종목 위주) · 가격 us_scan_full(폐지 포함) · S&P500 FDR US500.
    python research/n6_detail_1019.py
"""
import glob, sys
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
import numpy as np, pandas as pd
import FinanceDataReader as fdr

COST = 0.25
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def main():
    E = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(str(BASE / "data/us/analyst/earn_*.pkl")))], ignore_index=True)
    E["dt"] = pd.to_datetime(E["Earnings Date"], utc=True, errors="coerce")
    E = E.dropna(subset=["dt", "Surprise(%)"]).copy()
    E["edate"] = E.dt.dt.tz_convert("US/Eastern").dt.strftime("%Y%m%d")
    E = E.drop_duplicates(["ticker", "edate"], keep="last")
    A = pd.read_pickle(BASE / "data/us_scan_full.pkl")[["date", "ticker", "close", "rawclose", "volume", "buy", "amt20", "marcap", "n5", "n10", "n20", "n40", "n60", "up", "pref"]]
    A = A[((~A.pref.fillna(False)) & (A.rawclose >= 3)).fillna(False)].sort_values(["ticker", "date"]).reset_index(drop=True)
    A["amt_q"] = A.groupby("date").amt20.rank(pct=True)
    cal = np.array(sorted(A.date.unique())); DI = {d: i for i, d in enumerate(cal)}
    E["bdate"] = [cal[i] if i < len(cal) else None for i in np.searchsorted(cal, E.edate.values, "right")]
    E = E.dropna(subset=["bdate"])
    E["sur"] = E["Surprise(%)"].astype(float)
    E = E[E.groupby("bdate").sur.transform("size") >= 5]
    E["q"] = E.groupby("bdate").sur.rank(pct=True)
    A["_k"] = A.ticker + A.date
    A["peadq"] = A._k.map(dict(zip(E.ticker + E.bdate, E.q)))
    A["sur"] = A._k.map(dict(zip(E.ticker + E.bdate, E.sur)))
    g = A.groupby("ticker", sort=False)
    A["ret1"] = (A.close / g.close.shift(1) - 1) * 100
    b60 = g.close.shift(60)
    lo = g.close.transform(lambda s: s.rolling(61, min_periods=61).min())
    A["dn"] = (1 - lo / b60) * 100
    A["rc"] = (A.close - lo) / (b60 - lo)
    base = (A.amt_q >= 0.6) & (A.peadq >= 0.7) & (A.ret1 >= 3)
    nar = base & (A.dn >= 20) & (A.rc >= 0.25) & (A.rc < 1)
    IX = fdr.DataReader("US500", "2006-01-01"); IX = IX[IX.Close > 0]; IX["date"] = IX.index.strftime("%Y%m%d")
    IX["up"] = IX.Close > IX.Close.rolling(60).mean()
    ixc = dict(zip(IX.date, IX.Close)); ixd = IX.date.values; UP = dict(zip(IX.date, IX.up))

    def ix_ret(d, h):
        k = np.searchsorted(ixd, d)
        if k + h >= len(ixd): return np.nan
        return (IX.Close.values[k + h] / IX.Close.values[k] - 1) * 100

    def pick(mask):
        X = A[mask.fillna(False)].dropna(subset=["n60"])
        X = X[(X.buy > 0) & (X.date >= "20080101")].sort_values("date")
        keep, last = [], {}
        for t, d_, ix in zip(X.ticker.values, X.date.values, X.index):
            i = DI[d_]
            if last.get(t, -10 ** 9) >= i: continue
            last[t] = i + 60; keep.append(ix)
        Y = X.loc[keep].copy()
        for h in (5, 10, 20, 40, 60): Y["r%d" % h] = Y["n%d" % h].astype(float) - COST
        Y["spx"] = [ix_ret(d, 60) for d in Y.date]
        Y["x60"] = Y.r60 - Y.spx
        Y["mkt_up"] = Y.date.map(UP)
        Y["per"] = np.where(Y.date <= "20151231", "2008~15", np.where(Y.date <= "20221231", "2016~22", "2023~"))
        return Y

    Y = pick(nar); Y0 = pick(base & ~nar.fillna(False))
    Y.to_pickle(BASE / "research" / "cache" / "n6_detail.pkl")

    def st(z):
        r = z.r60
        if len(r) < 5: return "%d건" % len(r)
        w, l = r[r > 0].sum(), -r[r <= 0].sum()
        return "%d건 · 평균 %+.1f%% · 중앙 %+.1f%% · 승률 %.0f%% · PF %.2f · S&P 초과 %+.1f%%p" % (len(r), r.mean(), r.median(), (r > 0).mean() * 100, w / l if l else np.inf, z.x60.mean())

    P("## 1. 구간별 (60거래일 보유, 비용 0.25% 뒤)")
    P("| 구간 | [실적 서프라이즈] | 좁히기 전 나머지 신호(비교) |"); P("|---|---|---|")
    for p in ("2008~15", "2016~22", "2023~"):
        P("| %s | %s | %s |" % (p, st(Y[Y.per == p]), st(Y0[Y0.per == p])))
    P("| 전체 | %s | %s |" % (st(Y), st(Y0)))

    P("\n## 2. 해마다")
    P("| 해 | 건수 | 평균 | 중앙 | 승률 | S&P 초과 |"); P("|---|---|---|---|---|---|")
    for y, z in Y.groupby(Y.date.str[:4]):
        P("| %s | %d | %+.1f%% | %+.1f%% | %.0f%% | %+.1f%%p |" % (y, len(z), z.r60.mean(), z.r60.median(), (z.r60 > 0).mean() * 100, z.x60.mean()))

    P("\n## 3. 보유 기간별 평균 수익 흐름")
    P("| 보유 | 5일 | 10일 | 20일 | 40일 | 60일 |"); P("|---|---|---|---|---|---|")
    for nm, z in (("평균", Y), ("중앙", Y)):
        f = (lambda s: s.mean()) if nm == "평균" else (lambda s: s.median())
        P("| %s | %s |" % (nm, " | ".join("%+.1f%%" % f(z["r%d" % h]) for h in (5, 10, 20, 40, 60))))
    P("| 승률 | %s |" % " | ".join("%.0f%%" % ((Y["r%d" % h] > 0).mean() * 100) for h in (5, 10, 20, 40, 60)))

    P("\n## 4. 분포·쏠림")
    r = Y.r60.sort_values(ascending=False)
    P("상위 5%%(%d건)가 전체 수익의 %.0f%% · 상위 5%% 빼면 평균 %+.1f%% · 하위 10%% %+.1f%% · 최악 %+.1f%% · 최고 %+.1f%% · -30%%↓ 손실 %d건(%.0f%%)" % (
        max(1, len(r) // 20), r.head(max(1, len(r) // 20)).sum() / r.sum() * 100, r.iloc[len(r) // 20:].mean(), r.quantile(0.1), r.min(), r.max(), (r <= -30).sum(), (r <= -30).mean() * 100))

    P("\n## 5. 무엇이 성적을 가르나 (60일 평균 · 중앙 · 승률 · 건수)")
    def cut(nm, col, bins, labels):
        P("\n**%s**" % nm); P("| 구간 | 건수 | 평균 | 중앙 | 승률 | S&P 초과 |"); P("|---|---|---|---|---|---|")
        for lb, z in Y.groupby(pd.cut(Y[col], bins, labels=labels), observed=True):
            P("| %s | %d | %+.1f%% | %+.1f%% | %.0f%% | %+.1f%%p |" % (lb, len(z), z.r60.mean(), z.r60.median(), (z.r60 > 0).mean() * 100, z.x60.mean()))
    cut("서프라이즈 순위(그날 발표분 안)", "peadq", [0.69, 0.8, 0.9, 1.01], ["상위 20~30%", "상위 10~20%", "상위 10%"])
    cut("발표 다음 날 상승", "ret1", [3, 5, 10, 20, 1000], ["+3~5%", "+5~10%", "+10~20%", "+20%↑"])
    cut("60일 전 대비 하락 깊이", "dn", [20, 30, 40, 50, 100], ["-20~-30%", "-30~-40%", "-40~-50%", "-50%↓"])
    cut("하락분 회복 정도", "rc", [0.25, 0.5, 0.75, 1.0], ["1/4~1/2", "1/2~3/4", "3/4~거의 다"])
    cut("거래대금 순위", "amt_q", [0.59, 0.8, 0.9, 1.01], ["상위 20~40%", "상위 10~20%", "상위 10%"])
    Y["capb"] = Y.marcap / 1e9
    cut("시총($십억)", "capb", [0, 1, 5, 20, 1e6], ["$1B 미만", "$1~5B", "$5~20B", "$20B↑"])
    P("\n**S&P500 국면(60일선)**"); P("| 국면 | 건수 | 평균 | 중앙 | 승률 | S&P 초과 |"); P("|---|---|---|---|---|---|")
    for lb, z in Y.groupby(Y.mkt_up.map({True: "상승장", False: "하락장"})):
        P("| %s | %d | %+.1f%% | %+.1f%% | %.0f%% | %+.1f%%p |" % (lb, len(z), z.r60.mean(), z.r60.median(), (z.r60 > 0).mean() * 100, z.x60.mean()))
    (BASE / "research" / "cache" / "n6_detail_1019.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
