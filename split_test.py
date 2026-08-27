"""현재 1번 필터 전략에 5분할 매수 적용 백테스트 (단일매수 대비)
python split_test.py
"""
import csv, glob, io, sys, pickle
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
W, Q, B = 3, 40, 240

rows = []
for f in sorted(glob.glob(str(BASE / "data" / "20??-??.csv"))):
    with open(f, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["ticker"][-1] != "0" or not r["close"]: continue
            rows.append((r["ticker"], r["name"], r["date"], float(r["close"]), float(r["volume"] or 0),
                         float(r["frgn"]) if r["frgn"] else None))
df = pd.DataFrame(rows, columns=["ticker", "name", "date", "close", "volume", "frgn"]).sort_values(["ticker", "date"])
print(f"CSV {len(df):,}행 {df['date'].min()}~{df['date'].max()}", file=sys.stderr)

kospi = fdr.DataReader("KS11", "2025-11-01", "2026-08-28"); kospi["ma5"] = kospi["Close"].rolling(5).mean()
kdays = [d.strftime("%Y%m%d") for d in kospi.index]; kidx = {d: i for i, d in enumerate(kdays)}
kup = {d.strftime("%Y%m%d"): bool(r["Close"] > r["ma5"]) for d, r in kospi.iterrows()}

sig = {}
for t, g in df.groupby("ticker"):
    g = g.reset_index(drop=True); v = g["volume"]; f = g["frgn"]; c = g["close"]
    if len(g) < 300: continue
    quiet = v.shift(W).rolling(Q).mean() / v.shift(W + Q).rolling(B).mean()
    surge = v.rolling(W).mean() / v.shift(W).rolling(Q).mean()
    f5 = f.rolling(5).sum() / v.rolling(5).sum()
    fok = f.rolling(5).apply(lambda a: float(not np.isnan(a).any()), raw=True)
    amt = (c * v).shift(W).rolling(Q).mean() / 1e8
    m = (quiet < .5) & (surge >= 2) & (f5 >= .02) & (fok == 1) & (amt >= 3) & (g["date"] >= "20260105")
    if m.any(): sig[t] = (set(g.loc[m, "date"]), g["name"].iloc[0])

CF = BASE / "data" / "ohlc_cache.pkl"
cache = pickle.load(open(CF, "rb")) if CF.exists() else {}
def px(t):
    if t not in cache:
        try: cache[t] = fdr.DataReader(t, "2026-01-01", "2026-08-28")
        except Exception: cache[t] = pd.DataFrame()
    return cache[t]

trades = []
for t, (ds, name) in sig.items():
    last = -99
    for d in sorted(ds):
        i = kidx.get(d)
        if i is None or i < 1 or i + 1 >= len(kdays): continue
        if kdays[i - 1] in ds and not (i >= 2 and kdays[i - 2] in ds) and i - last >= 15:
            last = i; d_ = px(t)
            if len(d_) == 0: continue
            d_ = d_[d_.index >= pd.Timestamp(kdays[i + 1])]
            if len(d_) == 0 or d_.iloc[0]["Open"] <= 0: continue
            trades.append(dict(t=t, n=name, sig=d, o=float(d_.iloc[0]["Open"]), df=d_, up=kup.get(d, False)))
pickle.dump(cache, open(CF, "wb"))
print(f"진입 {len(trades)}건", file=sys.stderr)

def single(tr, hold=15, trail=None, sl=None):
    o, d = tr["o"], tr["df"]; hi = o
    if len(d) <= hold: return None
    for i in range(hold + 1):
        lo, h = d["Low"].iloc[i], d["High"].iloc[i]
        if sl and lo <= o * (1 - sl / 100): return (-sl, "손절", 1.0, -sl)
        if trail and hi > o and lo <= hi * (1 - trail / 100):
            r = (hi * (1 - trail / 100) / o - 1) * 100; return (r, "트레일", 1.0, r)
        hi = max(hi, h)
    r = (d["Close"].iloc[hold] / o - 1) * 100
    return (r, "만기", 1.0, r)

def split5(tr, steps=(0, 3, 6, 9, 12), hold=15, hard=20, trail=None):
    """1/5씩 -3/-6/-9/-12% 추가매수. 반환 (평단수익률, 사유, 투입비율, 전체자금수익률)"""
    o, d = tr["o"], tr["df"]
    if len(d) <= hold: return None
    prices = [o]; filled = 1; hi = o
    for i in range(hold + 1):
        lo, h = d["Low"].iloc[i], d["High"].iloc[i]
        while filled < 5 and lo <= o * (1 - steps[filled] / 100):
            prices.append(o * (1 - steps[filled] / 100)); filled += 1
        avg = float(np.mean(prices))
        if lo <= o * (1 - hard / 100):
            r = (o * (1 - hard / 100) / avg - 1) * 100
            return (r, "손절", filled / 5, r * filled / 5)
        if trail and hi > avg and lo <= hi * (1 - trail / 100):
            r = (hi * (1 - trail / 100) / avg - 1) * 100
            return (r, "트레일", filled / 5, r * filled / 5)
        hi = max(hi, h)
    avg = float(np.mean(prices)); r = (d["Close"].iloc[hold] / avg - 1) * 100
    return (r, "만기", filled / 5, r * filled / 5)

def stat(rs, idx=0):
    r = [x[idx] for x in rs if x]
    if len(r) < 10: return None
    w = [v for v in r if v > 0]; l = [v for v in r if v <= 0]
    return dict(n=len(r), avg=np.mean(r), win=len(w) / len(r) * 100, med=np.median(r),
                pf=(sum(w) / abs(sum(l))) if l else 99, worst=min(r))
def f(s): return f"{s['avg']:+.2f}% / {s['win']:.0f}% / PF {s['pf']:.2f}" if s else "-"

UP = [t for t in trades if t["up"]]
print(f"# 현재 1번 필터 + 5분할 매수 비교 — 2026-01~08, 2일 연속 진입 {len(trades)}건 (코스피 5일선 위 {len(UP)}건)\n")
print("표기: 평균 / 승률 / PF · 5분할은 [평단 기준]과 [전체자금 기준] 둘 다 표기\n")

print("## 1) 기본 비교 (15일 보유)\n")
print("| 방식 | 전체 | 코스피 5일선 위 | 중앙값 | 최악 |\n|---|---|---|---|---|")
cases = [("단일매수 · 15일 보유", lambda t: single(t, 15)),
         ("단일매수 · 15일 + 트레일10%", lambda t: single(t, 15, trail=10)),
         ("단일매수 · 15일 + 손절-10%", lambda t: single(t, 15, sl=10)),
         ("5분할 · 15일 [평단]", lambda t: split5(t, hold=15)),
         ("5분할 · 15일 [전체자금]", None),
         ("5분할 · 30일 [평단]", lambda t: split5(t, hold=30)),
         ("5분할 · 30일 [전체자금]", None)]
for lab, fn in cases:
    if fn is None: continue
    R = [fn(t) for t in trades]; RU = [fn(t) for t in UP]
    a = stat(R); u = stat(RU)
    print(f"| {lab} | {f(a)} | {f(u)} | {a['med']:+.2f}% | {a['worst']:+.1f}% |" if a else f"| {lab} | - | | | |")
    if "5분할" in lab:
        a2 = stat(R, 3); u2 = stat(RU, 3)
        lab2 = lab.replace("[평단]", "[전체자금]")
        print(f"| {lab2} | {f(a2)} | {f(u2)} | {a2['med']:+.2f}% | {a2['worst']:+.1f}% |" if a2 else "")

print("\n## 2) 분할 간격별 (15일 보유, 평단 기준)\n")
print("| 분할 간격 | 전체 | 코스피 5일선 위 | 전체자금 기준 | 평균 투입비율 |\n|---|---|---|---|---|")
for lab, steps in (("-3/-6/-9/-12%", (0, 3, 6, 9, 12)), ("-2/-4/-6/-8%", (0, 2, 4, 6, 8)),
                   ("-5/-10/-15/-20%", (0, 5, 10, 15, 20)), ("-4/-8/-12/-16%", (0, 4, 8, 12, 16))):
    R = [split5(t, steps=steps, hold=15) for t in trades]; RU = [split5(t, steps=steps, hold=15) for t in UP]
    a, u, a2 = stat(R), stat(RU), stat(R, 3)
    fill = np.mean([x[2] for x in R if x])
    print(f"| {lab} | {f(a)} | {f(u)} | {f(a2)} | {fill * 100:.0f}% |")

print("\n## 3) 분할 소진 분포 (-3/-6/-9/-12%, 15일)\n")
R = [split5(t, hold=15) for t in trades]; R = [x for x in R if x]
from collections import Counter
cn = Counter(round(x[2] * 5) for x in R)
print("| 소진 | 건수 | 비중 | 평단 평균수익 |\n|---|---|---|---|")
for k in sorted(cn):
    g = [x[0] for x in R if round(x[2] * 5) == k]
    print(f"| {k}차까지 | {cn[k]} | {cn[k]/len(R)*100:.0f}% | {np.mean(g):+.2f}% |")
hows = Counter(x[1] for x in R)
print("\n청산 사유: " + " · ".join(f"{k} {v}건({v/len(R)*100:.0f}%)" for k, v in hows.items()))

print("\n## 4) 자금 효율 비교 (같은 자금 100 기준, 코스피 5일선 위 매수만)\n")
print("| 방식 | 건당 계좌 기여 | 승률 | 최악 |\n|---|---|---|---|")
s1 = stat([single(t, 15) for t in UP]); s1t = stat([single(t, 15, trail=10) for t in UP])
s5 = stat([split5(t, hold=15) for t in UP], 3); s5b = stat([split5(t, hold=30) for t in UP], 3)
for lab, s in (("단일매수 15일", s1), ("단일매수 15일+트레일10%", s1t), ("5분할 15일", s5), ("5분할 30일", s5b)):
    print(f"| {lab} | {s['avg']:+.2f}% | {s['win']:.0f}% | {s['worst']:+.1f}% |" if s else f"| {lab} | - | | |")
