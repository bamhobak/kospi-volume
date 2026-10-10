# -*- coding: utf-8 -*-
"""A 해외지수 ETF 시가 괴리 (H0327, 2026-10-11).

주장: 국내 상장 해외지수 ETF 는 09:00~09:05 유동성공급자(LP) 호가 의무가 없어 시가가 공정가에서 벗어나 찍힌다 → 공정가 아래면 시가 매수.
공정가(근사) = 어제 ETF 종가 × (1 + 밤사이 미장 기초 ETF 종가→종가 등락) — 어제 15:30 종가 뒤 미장 정규장이 통째로 반영되니까.
(15:30~미장 개장 전 선물 움직임·환율 변화는 못 넣음 → 그만큼 오차. 환헤지(H) ETF 는 환율 영향 없음)
괴리 dev = 실제 시가 갭 - 공정 갭.  dev 가 크게 마이너스면 시가 매수 → 09:06·09:10·09:30 가격·종가 매도. 비용 0.05%(거래세 없음, 수수료·호가 반 칸).
1분봉 2022-12~ (m1_event 로 받음). 학습 2022-12~2024 · 검증 2025~.
    python research/etf_open.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "factory"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import common as C
import m1_event as ME

ETF = {"360750": ("TIGER 미국S&P500", "SPY"), "133690": ("TIGER 미국나스닥100", "QQQ"), "379800": ("KODEX 미국S&P500", "SPY"),
       "379810": ("KODEX 미국나스닥100", "QQQ"), "381180": ("TIGER 미국필라델피아반도체", "SOXX"), "381170": ("TIGER 미국테크TOP10", "QQQ"),
       "368590": ("RISE 미국나스닥100", "QQQ"), "360200": ("ACE 미국S&P500", "SPY"), "367380": ("ACE 미국나스닥100", "QQQ"),
       "448290": ("TIGER 미국S&P500(H)", "SPY"), "448300": ("TIGER 미국나스닥100(H)", "QQQ")}
COST = 0.05
M = C.toss(8.0)
days = []
for s in ("069500",):
    before = None
    for k in range(6):
        q = dict(symbol=s, interval="1d", count=200)
        if before: q["before"] = before
        r = M.get("/api/v1/candles", **q) or {}
        days += [x["timestamp"][:10].replace("-", "") for x in r.get("candles") or []]
        before = r.get("nextBefore")
        if not before: break
days = sorted(d for d in set(days) if d >= "20221201")
print("거래일 %d (%s~%s)" % (len(days), days[0], days[-1]), flush=True)
pairs = [(t, d) for t in ETF for d in days]
got, miss = ME.ensure("KR", pairs, log=lambda *a: print(*a, flush=True))
print("1분봉 받음 %d · 못 받음 %d" % (got, miss), flush=True)

US = pd.read_parquet(C.DATA / "us_daily.parquet")
US = US.sort_values(["sym", "date"]); US["r"] = US.groupby("sym").close.pct_change() * 100
rows = []
for t, (nm, us) in ETF.items():
    B = ME.bars("KR", t, days)
    if not B: print("  %s %s 1분봉 없음" % (t, nm)); continue
    u = US[US.sym == us].set_index("date").r
    ud = u.index.values
    prev_close = None
    for d in days:
        b = B.get(d)
        if b is None or len(b) < 100: prev_close = None; continue
        b = b[(b.hm >= "0901") & (b.hm <= "1531")]
        px = lambda hm: b[b.hm <= hm].c.iloc[-1] if (b.hm <= hm).any() else np.nan
        o, cl = b.o.iloc[0], b.c.iloc[-1]
        if prev_close:
            j = np.searchsorted(ud, d) - 1                           # 오늘(한국) 전 마지막 미장 세션
            ur = u.iloc[j] if j >= 0 else np.nan
            g = (o / prev_close - 1) * 100
            rows.append(dict(t=t, nm=nm, d=d, gap=g, fair=ur, dev=g - ur, v1=b.v.iloc[0],
                             r06=(px("0906") / o - 1) * 100 - COST, r10=(px("0910") / o - 1) * 100 - COST,
                             r30=(px("0930") / o - 1) * 100 - COST, rc=(cl / o - 1) * 100 - COST))
        prev_close = cl
R = pd.DataFrame(rows).dropna(subset=["dev"])
R.to_pickle(C.CACHE / "etf_open.pkl")
print("ETF-일 %d · 종목 %d" % (len(R), R.t.nunique()))
print("괴리 dev 분포: 1%% %.2f · 10%% %.2f · 중앙 %.2f · 90%% %.2f · 99%% %.2f · 시가 갭과 미장 등락 상관 %.2f" % (
    *R.dev.quantile([.01, .1, .5, .9, .99]), np.corrcoef(R.gap, R.fair)[0, 1]))


def line(nm, m):
    out = []
    for a, b in (("20221201", "20241231"), ("20250101", "20991231")):
        x = R[m & (R.d >= a) & (R.d <= b)]
        out.append("%4d %+5.2f/%+5.2f/%+5.2f/%+5.2f 승률(09:10) %3.0f%%" % (len(x), x.r06.mean(), x.r10.mean(), x.r30.mean(), x.rc.mean(), (x.r10 > 0).mean() * 100) if len(x) else "   0")
    print("%-34s | 학습 %s | 검증 %s" % (nm, *out), flush=True)


print("\n(수익 = 시가 매수 → 09:06 / 09:10 / 09:30 / 종가 매도, 비용 0.05 뺌)")
al = pd.Series(True, index=R.index)
line("전체", al)
for lo, hi in ((-99, -1.0), (-1.0, -0.5), (-0.5, -0.2), (-0.2, 0.2), (0.2, 0.5), (0.5, 1.0), (1.0, 99)):
    line("괴리 %+.1f < dev ≤ %+.1f" % (lo, hi), (R.dev > lo) & (R.dev <= hi))
line("괴리 ≤ -0.5 & 미장 -1%↓ 밤", (R.dev <= -0.5) & (R.fair <= -1))
line("괴리 ≤ -0.5 & 미장 -1%↑ 아닌 밤", (R.dev <= -0.5) & (R.fair > -1))
print("\n종목별(괴리 ≤ -0.5, 09:10 매도):")
for t, x in R[R.dev <= -0.5].groupby("t"):
    print("  %s %s: %d건 %+.2f%% 승률 %.0f%%" % (t, ETF[t][0], len(x), x.r10.mean(), (x.r10 > 0).mean() * 100))
