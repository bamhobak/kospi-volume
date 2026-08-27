"""2일 연속 신호 진입 후, 2거래일 뒤 손실 중 + 4일째 신호 유지 시 추가매수 효과 검증"""
import sqlite3, io, sys, pickle, statistics
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr
import collect
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
con = sqlite3.connect(collect.DB)
df = pd.read_sql("SELECT date,ticker,name,close,volume,frgn FROM daily WHERE ticker LIKE '%0' ORDER BY ticker,date", con)
kospi = fdr.DataReader("KS11", "2025-11-01", "2026-08-28"); kdays = [d.strftime("%Y%m%d") for d in kospi.index]; kidx = {d: i for i, d in enumerate(kdays)}
cache = pickle.load(open(BASE / "data" / "ohlc_cache.pkl", "rb"))
def px(t):
    if t not in cache:
        try: cache[t] = fdr.DataReader(t, "2026-01-01", "2026-08-28")
        except Exception: cache[t] = pd.DataFrame()
    return cache[t]
sig = {}   # ticker -> set(dates)
for t, g in df.groupby("ticker"):
    g = g.reset_index(drop=True); v = g["volume"].astype(float); f = g["frgn"]; c = g["close"].astype(float)
    if len(g) < 300: continue
    quiet = v.shift(3).rolling(40).mean() / v.shift(43).rolling(240).mean()
    surge = v.rolling(3).mean() / v.shift(3).rolling(40).mean()
    f5 = f.rolling(5).sum() / v.rolling(5).sum(); fok = f.rolling(5).apply(lambda a: float(not np.isnan(a).any()), raw=True)
    amt = (c * v).shift(3).rolling(40).mean() / 1e8
    m = (quiet < .5) & (surge >= 2) & (f5 >= .02) & (fok == 1) & (amt >= 3) & (g["date"] >= "20260105") & (g["date"] <= "20260826")
    if m.any(): sig[t] = (set(g.loc[m, "date"]), g["name"].iloc[0])
def ret_at(d, k): return (d.iloc[k]["Close"] / d.iloc[0]["Open"] - 1) * 100 if len(d) > k else None
rows = []
for t, (ds, name) in sig.items():
    last = -99
    for d in sorted(ds):
        i = kidx.get(d)
        if i is None or i - 1 < 0: continue
        if kdays[i - 1] in ds and not (i - 2 >= 0 and kdays[i - 2] in ds) and i - last >= 15:   # 정확히 2일 연속 첫 도달
            last = i
            if i + 1 >= len(kdays): continue
            buy = kdays[i + 1]; d_ = px(t); d_ = d_[d_.index >= pd.Timestamp(buy)]
            if len(d_) < 4 or d_.iloc[0]["Open"] <= 0: continue
            o = d_.iloc[0]["Open"]; r2 = (d_.iloc[2]["Close"] / o - 1) * 100          # 매수 후 2거래일 뒤 종가 수익률
            sig4 = kdays[i + 2] in ds and kdays[i + 1] in ds                                # 3·4일째 신호 유지(4일 연속)
            add_o = d_.iloc[3]["Open"] if len(d_) > 3 else None                             # 추가매수가: 5일째 시가
            r15 = ret_at(d_, 15) if len(d_) > 15 else (d_.iloc[-1]["Close"] / o - 1) * 100
            r15_add = ((d_.iloc[15]["Close"] if len(d_) > 15 else d_.iloc[-1]["Close"]) / add_o - 1) * 100 if add_o else None
            rows.append(dict(t=t, n=name, buy=buy, r2=r2, sig4=sig4, r15=r15, r15_add=r15_add))
R = pd.DataFrame(rows)
def st(x): x = [v for v in x if v is not None and not np.isnan(v)]; return f"{np.mean(x):+.1f}% / {np.mean([v > 0 for v in x]) * 100:.0f}% ({len(x)}건)" if x else "-"
print(f"2일 연속 신호 진입 {len(R)}건\n")
print("| 2거래일 뒤 상태 | 4일째 신호 | 건수 | 최초 매수분 15일 수익 | 추가매수분(5일째 시가) 15일 수익 |\n|---|---|---|---|---|")
for neg in (True, False):
    for s4 in (True, False):
        g = R[(R["r2"] < 0) == neg]; g = g[g["sig4"] == s4]
        print(f"| {'손실(-)' if neg else '이익(+)'} | {'유지(4일 연속)' if s4 else '소멸'} | {len(g)} | {st(g['r15'])} | {st(g['r15_add'])} |")
print(f"\n전체: 최초 매수분 15일 {st(R['r15'])}")
g = R[(R["r2"] < 0) & R["sig4"]]
if len(g): print("\n손실+4일 연속 케이스:\n" + "\n".join(f"- {r.n} ({r.buy[4:6]}/{r.buy[6:]}): 2일뒤 {r.r2:+.1f}% → 15일 최초분 {r.r15:+.1f}% / 추가분 {r.r15_add:+.1f}%" for r in g.itertuples()))
