"""연도별 백테스트 비교: 1번 필터(2일 연속 확인) 기준, 청산 규칙별 성과
사용: python multiyear.py 2023 2024 2025 2026
"""
import sqlite3, io, sys, pickle, statistics, datetime as dt
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr
import collect

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
YEARS = [int(y) for y in sys.argv[1:]] or [2023, 2024, 2025, 2026]
W, Q, B = 3, 40, 240

con = sqlite3.connect(collect.DB)
df = pd.read_sql("SELECT date,ticker,name,close,volume,frgn FROM daily WHERE ticker LIKE '%0' ORDER BY ticker,date", con)
print(f"DB 행 {len(df):,} · 기간 {df['date'].min()}~{df['date'].max()}", file=sys.stderr)

lo = f"{min(YEARS)-1}-11-01"; hi = f"{max(YEARS)+1}-03-31"
kospi = fdr.DataReader("KS11", lo, hi)
kospi["ma5"] = kospi["Close"].rolling(5).mean()
kdays = [d.strftime("%Y%m%d") for d in kospi.index]
kidx = {d: i for i, d in enumerate(kdays)}
kup = {d.strftime("%Y%m%d"): bool(r["Close"] > r["ma5"]) for d, r in kospi.iterrows()}

# ---- 신호 계산 (전 기간 한 번에) ----
sig = {}
for t, g in df.groupby("ticker"):
    g = g.reset_index(drop=True)
    v = g["volume"].astype(float); f = g["frgn"]; c = g["close"].astype(float)
    if len(g) < 300: continue
    quiet = v.shift(W).rolling(Q).mean() / v.shift(W + Q).rolling(B).mean()
    surge = v.rolling(W).mean() / v.shift(W).rolling(Q).mean()
    f5 = f.rolling(5).sum() / v.rolling(5).sum()
    fok = f.rolling(5).apply(lambda a: float(not np.isnan(a).any()), raw=True)
    amt = (c * v).shift(W).rolling(Q).mean() / 1e8
    m = (quiet < .5) & (surge >= 2) & (f5 >= .02) & (fok == 1) & (amt >= 3)
    if m.any(): sig[t] = (set(g.loc[m, "date"]), g["name"].iloc[0])
print(f"신호 있는 종목 {len(sig)}", file=sys.stderr)

cache_f = BASE / "data" / "ohlc_multi.pkl"
cache = pickle.load(open(cache_f, "rb")) if cache_f.exists() else {}
def px(t):
    if t not in cache:
        try: cache[t] = fdr.DataReader(t, lo, hi)
        except Exception: cache[t] = pd.DataFrame()
    return cache[t]

# ---- 2일 연속 확인 진입 ----
trades = []
for t, (ds, name) in sig.items():
    last = -99
    for d in sorted(ds):
        i = kidx.get(d)
        if i is None or i < 1 or i + 1 >= len(kdays): continue
        if kdays[i-1] in ds and not (i >= 2 and kdays[i-2] in ds) and i - last >= 15:
            last = i
            buy = kdays[i+1]
            d_ = px(t)
            if len(d_) == 0: continue
            d_ = d_[d_.index >= pd.Timestamp(buy)]
            if len(d_) == 0 or d_.iloc[0]["Open"] <= 0: continue
            trades.append(dict(t=t, n=name, sig=d, buy=buy, o=d_.iloc[0]["Open"], df=d_, up=kup.get(d, False), y=int(d[:4])))
pickle.dump(cache, open(cache_f, "wb"))

def sim(tr, hold=15, trail=None, sl=None):
    o, d_ = tr["o"], tr["df"]; hi = o
    if len(d_) <= hold: return None
    for i in range(hold + 1):
        r = d_.iloc[i]
        if sl and r["Low"] <= o * (1 - sl / 100): return -sl
        if trail and hi > o and r["Low"] <= hi * (1 - trail / 100): return (hi * (1 - trail / 100) / o - 1) * 100
        hi = max(hi, r["High"])
        if i == hold: return (r["Close"] / o - 1) * 100

def cell(tt, **kw):
    r = [x for x in (sim(t, **kw) for t in tt) if x is not None]
    if len(r) < 5: return f"표본부족({len(r)})"
    return f"{sum(r)/len(r):+.1f}% / {sum(v>0 for v in r)/len(r)*100:.0f}% ({len(r)})"

print(f"# 연도별 백테스트 — 1번 필터 2일 연속 확인 후 다음날 시가 매수\n")
print(f"총 진입 {len(trades)}건\n")
print("## 연도별 성과\n")
print("| 연도 | 진입 | 코스피 연간 | 10일 | 15일 | 20일 | 15일+트레일10% | 15일+손절-10% |")
print("|---|---|---|---|---|---|---|---|")
for y in YEARS:
    tt = [t for t in trades if t["y"] == y]
    if not tt: print(f"| {y} | 0 | | | | | | |"); continue
    k = kospi[kospi.index.year == y]
    kr = (k["Close"].iloc[-1] / k["Close"].iloc[0] - 1) * 100 if len(k) > 1 else 0
    print(f"| {y} | {len(tt)} | {kr:+.1f}% | {cell(tt, hold=10)} | {cell(tt, hold=15)} | {cell(tt, hold=20)} | {cell(tt, hold=15, trail=10)} | {cell(tt, hold=15, sl=10)} |")
allt = [t for t in trades if t["y"] in YEARS]
print(f"| **전체** | {len(allt)} | | {cell(allt, hold=10)} | {cell(allt, hold=15)} | {cell(allt, hold=20)} | {cell(allt, hold=15, trail=10)} | {cell(allt, hold=15, sl=10)} |")

print("\n## 시장 필터(코스피 > 5일선) 효과 — 15일 보유\n")
print("| 연도 | 5일선 위 진입 | 성과 | 5일선 아래 진입 | 성과 |")
print("|---|---|---|---|---|")
for y in YEARS:
    tt = [t for t in trades if t["y"] == y]
    up = [t for t in tt if t["up"]]; dn = [t for t in tt if not t["up"]]
    print(f"| {y} | {len(up)} | {cell(up, hold=15)} | {len(dn)} | {cell(dn, hold=15)} |")
up = [t for t in allt if t["up"]]; dn = [t for t in allt if not t["up"]]
print(f"| **전체** | {len(up)} | {cell(up, hold=15)} | {len(dn)} | {cell(dn, hold=15)} |")

print("\n## 시장 필터 + 청산 규칙 (5일선 위 매수만)\n")
print("| 연도 | 건수 | 10일 | 15일 | 15일+트레일10% | 15일+손절-10% | 20일+트레일10% |")
print("|---|---|---|---|---|---|---|")
for y in YEARS:
    tt = [t for t in trades if t["y"] == y and t["up"]]
    if len(tt) < 3: print(f"| {y} | {len(tt)} | 표본부족 | | | | |"); continue
    print(f"| {y} | {len(tt)} | {cell(tt, hold=10)} | {cell(tt, hold=15)} | {cell(tt, hold=15, trail=10)} | {cell(tt, hold=15, sl=10)} | {cell(tt, hold=20, trail=10)} |")
print(f"| **전체** | {len(up)} | {cell(up, hold=10)} | {cell(up, hold=15)} | {cell(up, hold=15, trail=10)} | {cell(up, hold=15, sl=10)} | {cell(up, hold=20, trail=10)} |")

print("\n## 월별 진입 분포\n")
print("| 연도 | " + " | ".join(f"{m}월" for m in range(1, 13)) + " |")
print("|---" * 13 + "|")
for y in YEARS:
    row = [str(sum(1 for t in trades if t["y"] == y and int(t["sig"][4:6]) == m)) for m in range(1, 13)]
    print(f"| {y} | " + " | ".join(row) + " |")

print("\n## 상위/하위 거래 (15일 보유)\n")
rr = [(sim(t, hold=15), t) for t in allt]
rr = [(v, t) for v, t in rr if v is not None]
rr.sort(key=lambda x: -x[0])
print("**상위 10**\n")
print("| 매수일 | 종목 | 수익률 | 시장 |\n|---|---|---|---|")
for v, t in rr[:10]: print(f"| {t['buy'][:4]}-{t['buy'][4:6]}-{t['buy'][6:]} | {t['n']} | {v:+.1f}% | {'▲' if t['up'] else '▼'} |")
print("\n**하위 10**\n")
print("| 매수일 | 종목 | 수익률 | 시장 |\n|---|---|---|---|")
for v, t in rr[-10:]: print(f"| {t['buy'][:4]}-{t['buy'][4:6]}-{t['buy'][6:]} | {t['n']} | {v:+.1f}% | {'▲' if t['up'] else '▼'} |")
