# -*- coding: utf-8 -*-
"""생존편향 측정 — 폐지 종목을 포함했을 때 필터 성과가 얼마나 달라지는가"""
import io, pickle, sqlite3, sys
import numpy as np, pandas as pd
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
W_SURGE, W_QUIET, W_BASE, NB, MINGAP = 3, 40, 240, 45, 15

def build(df, rs_map, K20, tag):
    SIG = []
    for t, g in df.groupby("ticker", sort=False):
        if len(g) < W_BASE + W_QUIET + W_SURGE + 5: continue
        O, H, L, C, D = (g[c].values for c in ("open", "high", "low", "close", "date"))
        V = pd.Series(g["volume"].values, dtype="float64"); Cs = pd.Series(C, dtype="float64")
        F = pd.Series(g["frgn"].values, dtype="float64").fillna(0)
        aw = V.rolling(W_SURGE).mean(); a1 = V.shift(W_SURGE).rolling(W_QUIET).mean()
        a6 = V.shift(W_SURGE + W_QUIET).rolling(W_BASE).mean()
        quiet = (a1 / a6).values; surge = (aw / a1).values
        v5 = V.rolling(5).sum(); fwp = (F.rolling(5).sum() / v5 * 100).values
        amt = ((V * Cs).shift(W_SURGE).rolling(W_QUIET).mean() / 1e8).values
        ret3 = (Cs / Cs.shift(3) - 1).values * 100; ret10 = (Cs / Cs.shift(10) - 1).values * 100
        last = -99
        for j in range(len(g) - 1):
            if j - last < MINGAP: continue
            if not np.isfinite(quiet[j]) or not np.isfinite(surge[j]): continue
            if surge[j] < 2 or quiet[j] > 0.7: continue
            o0 = O[j + 1]
            if o0 is None or not np.isfinite(o0) or o0 <= 0: continue
            d = D[j]; e = min(j + 1 + NB, len(g))
            SIG.append(dict(t=t, d=d, y=int(d[:4]), src=tag,
                H=(H[j+1:e]/o0-1)*100, L=(L[j+1:e]/o0-1)*100, C=(C[j+1:e]/o0-1)*100,
                quiet=float(quiet[j]), surge=float(surge[j]),
                fwp=float(fwp[j]) if np.isfinite(fwp[j]) else 0.0,
                amt=float(amt[j]) if np.isfinite(amt[j]) else 0.0,
                ret3=float(ret3[j]) if np.isfinite(ret3[j]) else 0.0,
                ret10=float(ret10[j]) if np.isfinite(ret10[j]) else 0.0,
                rs=rs_map.get((d, t)), k20=bool(K20.get(d, False)), pref=not t.endswith("0"),
                ndays=e - (j + 1)))
            last = j
    return SIG

import FinanceDataReader as fdr
ki = fdr.DataReader("KS11", "2017-01-01"); ki = ki[ki["Close"] > 0]
ki.index = ki.index.strftime("%Y%m%d")
K20 = (ki["Close"] > ki["Close"].rolling(20).mean()).to_dict()
Z = pickle.load(open("data/sector_index.pkl", "rb")); RS = Z["upjong"]["rs20"]
sec = pd.read_sql("SELECT ticker,gname FROM sector WHERE kind='upjong'",
                  sqlite3.connect("file:data/kospi.db?mode=ro", uri=True))
T2G = dict(sec.values)
def rsmap(tickers):
    m = {}
    for t in tickers:
        g = T2G.get(t)
        if not g or g == "기타" or g not in RS.columns: continue
        s = RS[g].dropna()
        for d, v in s.items(): m[(d, t)] = float(v)
    return m

dl = pd.read_sql("SELECT date,ticker,close,volume,frgn,open,high,low FROM daily ORDER BY ticker,date",
                 sqlite3.connect("file:data/delisted.db?mode=ro", uri=True))
print(f"폐지 종목 {dl.ticker.nunique()}개 · {len(dl):,}행")
SD = build(dl, rsmap(dl.ticker.unique()), K20, "폐지")
print(f"폐지 종목 신호: {len(SD)}건")
SL = [s for s in pickle.load(open("data/sig_2018.pkl", "rb")) if len(s["C"]) >= 2]
for s in SL: s["src"] = "생존"
ALL = SL + [s for s in SD if len(s["C"]) >= 2]

def cost(a):
    a = a or 3
    return 0.18 + (0.20 if a >= 100 else 0.30 if a >= 50 else 0.50 if a >= 20 else 0.70 if a >= 10 else 1.00)
def ev(s, h, sl, tp):
    H, L, C = s["H"], s["L"], s["C"]; n = min(h, len(C) - 1); c = cost(s["amt"])
    for i in range(n + 1):
        if sl and L[i] <= -sl: return -sl - c
        if tp and H[i] >= tp: return tp - c
        if i == n: return C[i] - c
def stat(P, h, sl, tp):
    if not P: return None
    r = np.array([ev(s, h, sl, tp) for s in P]); w, l = r[r > 0], r[r <= 0]
    return dict(n=len(r), avg=r.mean(), med=np.median(r), win=len(w) / len(r) * 100,
                pf=(w.sum() / abs(l.sum())) if len(l) else 99)
F1 = lambda s: (s["quiet"] < 0.5 and s["surge"] >= 2 and s["fwp"] >= 2 and s["amt"] >= 50
                and 0 <= s["ret10"] <= 20 and s["k20"] and not s["pref"]
                and s["rs"] is not None and s["rs"] > 0)
F2 = lambda s: (s["quiet"] < 0.4 and s["surge"] >= 2 and s["fwp"] >= 2 and s["amt"] >= 3
                and s["ret3"] <= 0 and not s["pref"])
print("\n## 생존편향 측정\n")
print("| 필터 | 구성 | 건수 | 순수익 | 중앙값 | 승률 | PF |\n|---|---|---|---|---|---|---|")
for lab, fn, h, sl, tp in [("1번", F1, 10, 15, 30), ("2번", F2, 10, 10, None)]:
    surv = [s for s in ALL if s["src"] == "생존" and fn(s)]
    dead = [s for s in ALL if s["src"] == "폐지" and fn(s)]
    both = surv + dead
    for nm, P in [("현재 상장분만 (기존)", surv), ("**폐지 포함 (실제)**", both)]:
        a = stat(P, h, sl, tp)
        if a: print(f"| {lab} | {nm} | {a['n']} | **{a['avg']:+.2f}%** | {a['med']:+.2f}% | {a['win']:.0f}% | {a['pf']:.2f} |")
    a = stat(dead, h, sl, tp)
    print(f"| {lab} | └ 폐지 종목만 | {len(dead)} | " + (f"{a['avg']:+.2f}% | {a['med']:+.2f}% | {a['win']:.0f}% | {a['pf']:.2f} |" if a else "- | - | - | - |"))
