# -*- coding: utf-8 -*-
"""미장판 — 같은 업종 안에서 더 빠진·더 오른 종목, 기간 수익률 스윙 (2026-11-16 사용자 "미장도 같은 방식으로"). theme_swing_1116 과 같은 정의.
자료: data/us/raw(살아 있는 종목) + tiingo_dead.db(폐지) 수정주가 2007~ · 업종 = data/us/tickers.csv Industry(지금 상장 종목 6,085개의 지금 업종 —
      폐지 종목은 업종이 없어 빠진다 → 살아남은 종목 편향: 절대 수익은 부풀 수 있음, '같은 업종 대비'를 볼 것).
유니버스: 종가 $5↑ · 20일 거래대금 $100만↑ · 업종 안 4종목↑ · 5거래일마다 신호 · 매수 = 신호 날 종가 → H일 뒤 종가 · 비용 0.20.
    python research/memguard.py research/theme_swing_us_1116.py
"""
import math, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path[:0] = [str(ROOT)]; sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import quiet_break_1112 as Q, quiet_break_us_1112 as QU
Q.COST = 0.20
OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))
PER = (("20160101", "20221231"), ("20230101", "20991231"))
t_ = lambda s: s.mean() / s.std(ddof=1) * math.sqrt(len(s)) if len(s) > 2 and s.std(ddof=1) > 0 else 0
I = pd.read_csv(BASE / "data" / "us" / "tickers.csv").rename(columns={"Symbol": "ticker", "Industry": "g"})[["ticker", "g"]].dropna()
need = set(I.ticker); cal = None; parts = []
for D in QU.batches():
    if cal is None:
        ds = sorted(D.date.unique()); cal = set(ds[::5])
    D = D[D.ticker.isin(need)]
    if not len(D): continue
    D = Q.build(D.reset_index(drop=True))
    for h in (5, 20, 60): D["f%d" % h] = D["f%d" % h].clip(-95, 500)
    cs = D.lr.groupby(D.ticker).cumsum()
    for L in (5, 20, 60): D["r%d" % L] = ((np.exp(cs - cs.groupby(D.ticker).shift(L)) - 1) * 100).clip(-95, 1000).astype("float32")
    parts.append(D[(D.date >= "20150101") & D.date.isin(cal) & (D.close >= 5) & (D.a20 >= 1e6) & (D.change.abs() < 40)][["ticker", "date", "r5", "r20", "r60", "f5", "f20", "f60"]])
D = pd.concat(parts, ignore_index=True).merge(I, on="ticker")
for h in (5, 20, 60): D["m%d" % h] = D.groupby("date")["f%d" % h].transform("mean")
P("미장 업종 %d개 · 종목 %d · 종목-일 %d · %s~%s\n" % (D.g.nunique(), D.ticker.nunique(), len(D), D.date.min(), D.date.max()))
P("| 기간 L | 업종 상태 | 고르는 종목 | 보유 | 학습 건·날 | 학습 건당 | 날 바구니(t) | 시장 대비 | 같은 업종 대비(t) | 검증 건·날 | 검증 건당 | 날 바구니(t) | 시장 대비 | 같은 업종 대비(t) |"); P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for L, Xc in ((5, 5), (20, 10), (60, 20)):
    r = "r%d" % L
    Y = D.dropna(subset=[r]).copy()
    g = Y.groupby(["date", "g"])
    Y["n"] = g.ticker.transform("size"); Y = Y[Y.n >= 4]; g = Y.groupby(["date", "g"])
    Y["tg"] = g[r].transform("median"); Y["rel"] = Y[r] - Y.tg
    Y["lo"] = g[r].rank(method="first"); Y["hi"] = g[r].rank(method="first", ascending=False)
    for h in (5, 20, 60):
        f = "f%d" % h; s, n = g[f].transform("sum"), g[f].transform("count")
        Y["p%d" % h] = (s - Y[f].fillna(0)) / (n - Y[f].notna()).replace(0, np.nan)
    for dn, dm in (("뜸(+%d%%↑)" % Xc, Y.tg >= Xc), ("빠짐(-%d%%↓)" % Xc, Y.tg <= -Xc), ("아무 때", Y.tg > -999)):
        for pn, pm in (("가장 뒤처진 1종목", Y.lo == 1), ("가장 앞선 1종목", Y.hi == 1), ("업종보다 %d%%p↓" % Xc, Y.rel <= -Xc), ("업종보다 %d%%p↑" % Xc, Y.rel >= Xc)):
            Z = Y[dm & pm]
            for h in (5, 20, 60):
                f = "f%d" % h; cells = []
                for a, b in PER:
                    z = Z[(Z.date >= a) & (Z.date <= b)].dropna(subset=[f])
                    if len(z) < 30: cells = None; break
                    d = z.groupby("date")[f].mean(); e = z.assign(e=z[f] - z["p%d" % h]).groupby("date").e.mean().dropna()
                    cells.append("%d·%d | %+.2f%% | %+.2f%% (%.1f) | %+.2f | %+.2f (%.1f)" % (len(z), len(d), z[f].mean(), d.mean(), t_(d), (z[f] - z["m%d" % h]).mean(), e.mean(), t_(e)))
                if cells: P("| %d일 | %s | %s | %d일 | %s | %s |" % (L, dn, pn, h, cells[0], cells[1]))
(ROOT / "theme_swing_us_1116.out").write_text("\n".join(OUT), encoding="utf-8")
