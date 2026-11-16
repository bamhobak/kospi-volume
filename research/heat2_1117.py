# -*- coding: utf-8 -*-
"""H0425 단기과열 지정 — 단일가 3일 동안 오르는 게 진짜인가 뜯어보기 (2026-11-17).
함정 점검: ① 상한가로 열려 못 사는 날 빼기(시가 갭 ≥ +25% 또는 시가=고가=저가) ② 우선주 잘못 맞춤 막기(5일 +15%↑만) ③ 대박 몇 건 몫(위 1%·5% 자르기)
④ 연도별 ⑤ 사는 때·파는 때 변형 ⑥ 지정 전 오름폭·시가 갭 구간 ⑦ 거래대금(단일가 날 하루 거래대금 — 200만 원이 몇 %인가)
"""
import math, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parent.parent; COST = 0.23
OUT = []; P_ = lambda s="": (OUT.append(s), print(s, flush=True))
t_ = lambda s: s.mean() / s.std(ddof=1) * math.sqrt(len(s)) if len(s) > 2 and s.std(ddof=1) > 0 else 0.0
P = pd.read_pickle(BASE / "research" / "cache" / "factory_px.pkl"); P = P[P.date >= "20151001"]
cal = sorted(P.date.unique()); ci = {d: i for i, d in enumerate(cal)}; tk = sorted(P.ticker.unique()); ti = {t: i for i, t in enumerate(tk)}
W = lambda col: P.pivot(index="date", columns="ticker", values=col).reindex(index=cal, columns=tk).values.astype(np.float64)
OP, HI, LO, CL = W("open"), W("high"), W("low"), W("close"); del P; nd, nt = CL.shape
c = sqlite3.connect("file:%s?mode=ro" % (BASE / "data" / "dart" / "kind_time.db"), uri=True)
K = pd.read_sql("select day, hm, kcode, market, title from kind where title = '단기과열종목(3거래일 단일가매매) 지정'", c); c.close()
K["t"] = K.kcode + "0"; K = K[K.t.isin(ti) & K.day.isin(ci)].drop_duplicates(["day", "t"])
K["i"] = K.day.map(ci); K["j"] = K.t.map(ti); K = K[(K.i >= 6) & (K.i < nd - 14)]
g = lambda A, k: A[K.i.values + k, K.j.values]
K["c0"] = g(CL, 0); K["r5"] = (g(CL, 0) / g(CL, -5) - 1) * 100
for k in (1, 2, 3, 4): K["o%d" % k], K["h%d" % k], K["l%d" % k], K["c%d" % k] = g(OP, k), g(HI, k), g(LO, k), g(CL, k)
for k in (6, 8, 13): K["c%d" % k] = g(CL, k)
K["gap1"] = (K.o1 / K.c0 - 1) * 100; K["gap2"] = (K.o2 / K.c1 - 1) * 100
K["lock1"] = (K.gap1 >= 25) | ((K.o1 == K.h1) & (K.h1 == K.l1) & (K.gap1 > 10))
K["lockc1"] = (K.c1 / K.c0 - 1 >= 0.295) & (K.c1 == K.h1)                    # D+1 종가 상한가 — 종가에 못 삼
n0 = len(K); K = K[(K.c0 >= 1000) & (K.r5 >= 15) & K.o1.notna()]
P_("# H0425 단기과열 지정 — 뜯어보기\n"); P_("지정 %d건 → 5일 +15%%↑·1000원↑·D+1 거래 %d건 · 공시 시각: %s · D+1 시가 상한가(못 삼) %d건 · D+1 종가 상한가 %d건" % (
    n0, len(K), K.hm.str[:2].value_counts().head(3).to_dict(), K.lock1.sum(), K.lockc1.sum()))
ret = lambda a, b: ((b / a - 1) * 100 - COST)
V = {"A 말한 판: D+1 시가→D+3 종가": (ret(K.o1, K.c3), ~K.lock1), "B D+1 시가→D+1 종가": (ret(K.o1, K.c1), ~K.lock1), "C D+1 시가→D+2 종가": (ret(K.o1, K.c2), ~K.lock1),
     "D D+1 종가→D+3 종가": (ret(K.c1, K.c3), ~K.lockc1), "E D+1 종가→D+2 종가": (ret(K.c1, K.c2), ~K.lockc1), "F D+2 시가→D+3 종가": (ret(K.o2, K.c3), K.gap2 < 25),
     "G D+2 종가→D+3 종가": (ret(K.c2, K.c3), (K.c2 / K.c1 - 1 < 0.295)), "H D+1 종가→D+2 시가(밤사이)": (ret(K.c1, K.o2), ~K.lockc1), "I D+3 종가→D+4 시가": (ret(K.c3, K.o4), K.c3 / K.c2 - 1 < 0.295),
     "J D+1 시가→D+4 시가": (ret(K.o1, K.o4), ~K.lock1), "(참고) 상한가로 열린 것만 A": (ret(K.o1, K.c3), K.lock1)}
PER = (("학습 16~22", "20160101", "20221231"), ("검증 23~", "20230101", "20991231"))


def line(nm, r, m, Z=None):
    Z = K if Z is None else Z; cells = []
    for _, a, b in PER:
        s = r[m & (Z.day >= a) & (Z.day <= b)].dropna()
        if len(s) < 15: cells.append("%d건 | – | – | – | –" % len(s)); continue
        d = s.groupby(Z.day[s.index]).mean(); q99, q95 = s.quantile(0.99), s.quantile(0.95)
        yr = " ".join("%s:%+.1f(%d)" % (y[2:], v, n) for y, v, n in zip(*[s.groupby(Z.day[s.index].str[:4]).mean().index, s.groupby(Z.day[s.index].str[:4]).mean().values, s.groupby(Z.day[s.index].str[:4]).size().values]))
        cells.append("%d | %+.2f%% (중앙 %+.2f·승 %.0f%%) | %+.2f%% (t%.1f) | %+.2f / %+.2f | %s" % (len(s), s.mean(), s.median(), (s > 0).mean() * 100, d.mean(), t_(d), s[s < q99].mean(), s[s < q95].mean(), yr))
    P_("| %s | %s | %s |" % (nm, cells[0], cells[1]))


HD = "| 판 | 학습 건 | 건당(중앙·승률) | 날 바구니(t) | 위 1%·5% 뺀 평균 | 연도별(건) | 검증 건 | 건당(중앙·승률) | 날 바구니(t) | 위 1%·5% 뺀 평균 | 연도별(건) |\n|---|---|---|---|---|---|---|---|---|---|---|"
P_("\n## 1. 사는 때·파는 때 (못 사는 상한가 뺌)\n"); P_(HD)
for nm, (r, m) in V.items(): line(nm, r, m)
rA, mA = V["A 말한 판: D+1 시가→D+3 종가"]; rD, mD = V["D D+1 종가→D+3 종가"]
P_("\n## 2. A·D 판 쪼개기\n"); P_(HD)
for nm, m in (("D+1 시가 갭 ≤ -5%", K.gap1 <= -5), ("갭 -5~0%", (K.gap1 > -5) & (K.gap1 <= 0)), ("갭 0~+5%", (K.gap1 > 0) & (K.gap1 <= 5)), ("갭 +5~25%", (K.gap1 > 5) & (K.gap1 < 25)),
              ("지정 전 5일 +15~40%", K.r5 < 40), ("5일 +40~70%", (K.r5 >= 40) & (K.r5 < 70)), ("5일 +70%↑", K.r5 >= 70), ("유가증권", K.market == "유가증권"), ("코스닥", K.market == "코스닥"),
              ("1만원↑", K.c0 >= 10000), ("1만원↓", K.c0 < 10000)):
    line("A · " + nm, rA, mA & m)
d1 = (K.c1 / K.o1 - 1) * 100
for nm, m in (("D+1 장중 -5%↓", d1 <= -5), ("D+1 장중 -5~0%", (d1 > -5) & (d1 <= 0)), ("D+1 장중 0~+5%", (d1 > 0) & (d1 <= 5)), ("D+1 장중 +5%↑", d1 > 5)):
    line("D · " + nm, rD, mD & m)
# 거래대금: kospi.db / kosdaq.db 일봉 volume × close
try:
    fr = []
    for db in ("kospi.db", "kosdaq.db"):
        cc = sqlite3.connect("file:%s?mode=ro" % (BASE / "data" / db), uri=True)
        tb = [r[0] for r in cc.execute("select name from sqlite_master where type='table'")]
        cols = [r[1] for r in cc.execute("pragma table_info(daily)")] if "daily" in tb else []
        print(db, tb[:8], cols)
        if "daily" in tb and "amount" in cols: fr.append(pd.read_sql("select ticker t, date d, amount a from daily where date>='20160101'", cc))
        elif "daily" in tb: fr.append(pd.read_sql("select ticker t, date d, volume*close a from daily where date>='20160101'", cc))
    A_ = pd.concat(fr); A_["d"] = A_.d.astype(str).str.replace("-", ""); am = A_.set_index(["t", "d"]).a
    for k in (1, 2, 3):
        K["a%d" % k] = [am.get((t, cal[i + k]), np.nan) for t, i in zip(K.t.values, K.i.values)]
    P_("\n## 3. 단일가 날 하루 거래대금(억): D+1 중앙 %.0f · 아래 10%% %.1f · D+3 중앙 %.0f · 아래 10%% %.1f — 10억↓ 비율 D+1 %.0f%% · D+3 %.0f%%" % (
        K.a1.median() / 1e8, K.a1.quantile(.1) / 1e8, K.a3.median() / 1e8, K.a3.quantile(.1) / 1e8, (K.a1 < 1e9).mean() * 100, (K.a3 < 1e9).mean() * 100))
    P_(HD)
    for nm, m in (("D+1 거래대금 50억↑", K.a1 >= 5e9), ("10~50억", (K.a1 >= 1e9) & (K.a1 < 5e9)), ("10억↓", K.a1 < 1e9)): line("A · " + nm, rA, mA & m)
except Exception as e: P_("거래대금 못 읽음: %r" % e)
K.to_pickle("C:/temp/kp/heat_ev.pkl")
(BASE / "research" / "reports" / "heat2_1117.md").write_text("\n".join(OUT), encoding="utf-8")
