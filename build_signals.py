# -*- coding: utf-8 -*-
"""2018~2026 코스피 신호 캐시 생성 (필터 1·2 재검증용)
   기존 sig3_cache 와 동일 로직 + 업종 상대강도(rs) 결합
   출력: data/sig_2018.pkl
"""
import io, pickle, sqlite3, sys
import numpy as np, pandas as pd
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

W_SURGE, W_QUIET, W_BASE = 3, 40, 240
NB = 45                     # 매수 후 추적 거래일 수
MINGAP = 15                 # 같은 종목 재신호 최소 간격

con = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True)
df = pd.read_sql("""SELECT date,ticker,name,close,volume,frgn,organ,open,high,low
                    FROM daily WHERE market='KOSPI' ORDER BY ticker,date""", con)
con.close()
print(f"입력 {len(df):,}행 · {df.ticker.nunique()}종목 · {df.date.min()}~{df.date.max()}")

# 코스피 지수 5/20일선
import FinanceDataReader as fdr
ki = fdr.DataReader("KS11", "2017-01-01")
ki = ki[ki["Close"] > 0]
ki.index = ki.index.strftime("%Y%m%d")
K5 = (ki["Close"] > ki["Close"].rolling(5).mean()).to_dict()
K20 = (ki["Close"] > ki["Close"].rolling(20).mean()).to_dict()

# 업종 상대강도
Z = pickle.load(open("data/sector_index.pkl", "rb"))
RS = Z["upjong"]["rs20"]
sec = pd.read_sql("SELECT ticker,gname FROM sector WHERE kind='upjong'",
                  sqlite3.connect("file:data/kospi.db?mode=ro", uri=True))
T2G = dict(sec.values)

SIG = []
for t, g in df.groupby("ticker", sort=False):
    if len(g) < W_BASE + W_QUIET + W_SURGE + 5: continue
    nm = g["name"].iloc[-1]
    O, H, L, C, D = (g[c].values for c in ("open", "high", "low", "close", "date"))
    V, F, R = g["volume"].values, g["frgn"].values, g["organ"].values
    V = pd.Series(V, dtype="float64"); Cs = pd.Series(C, dtype="float64")
    F = pd.Series(F, dtype="float64").fillna(0); Rr = pd.Series(R, dtype="float64").fillna(0)
    aw = V.rolling(W_SURGE).mean()
    a1 = V.shift(W_SURGE).rolling(W_QUIET).mean()
    a6 = V.shift(W_SURGE + W_QUIET).rolling(W_BASE).mean()
    quiet = (a1 / a6).values; surge = (aw / a1).values
    v5 = V.rolling(5).sum(); f5 = F.rolling(5).sum(); r5 = Rr.rolling(5).sum()
    fwp = (f5 / v5 * 100).values; owp = (r5 / v5 * 100).values
    amt = ((V * Cs).shift(W_SURGE).rolling(W_QUIET).mean() / 1e8).values      # 잠잠창 평균 거래대금(억)
    ret3 = (Cs / Cs.shift(3) - 1).values * 100
    ret10 = (Cs / Cs.shift(10) - 1).values * 100
    gname = T2G.get(t)
    last = -99
    for j in range(len(g) - 1):
        if j - last < MINGAP: continue
        if not np.isfinite(quiet[j]) or not np.isfinite(surge[j]): continue
        if surge[j] < 2 or quiet[j] > 0.7: continue                # 넉넉한 기본 풀
        o0 = O[j + 1]
        if o0 is None or not np.isfinite(o0) or o0 <= 0: continue
        d = D[j]
        rs = np.nan
        if gname and gname != "기타" and gname in RS.columns and d in RS.index:
            rs = RS.at[d, gname]
        e = min(j + 1 + NB, len(g))
        SIG.append(dict(t=t, n=nm, d=d, y=int(d[:4]),
            H=(H[j+1:e]/o0-1)*100, L=(L[j+1:e]/o0-1)*100, C=(C[j+1:e]/o0-1)*100,
            quiet=float(quiet[j]), surge=float(surge[j]),
            fwp=float(fwp[j]) if np.isfinite(fwp[j]) else 0.0,
            owp=float(owp[j]) if np.isfinite(owp[j]) else 0.0,
            amt=float(amt[j]) if np.isfinite(amt[j]) else 0.0,
            ret3=float(ret3[j]) if np.isfinite(ret3[j]) else 0.0,
            ret10=float(ret10[j]) if np.isfinite(ret10[j]) else 0.0,
            rs=float(rs) if np.isfinite(rs) else None,
            k5=bool(K5.get(d, False)), k20=bool(K20.get(d, False)),
            pref=not t.endswith("0")))
        last = j
pickle.dump(SIG, open("data/sig_2018.pkl", "wb"))
ys = pd.Series([s["y"] for s in SIG]).value_counts().sort_index()
print(f"\n신호 {len(SIG):,}건 · 연도별:")
for y, c in ys.items(): print(f"   {y}: {c:,}")
print(f"rs 있는 신호: {sum(1 for s in SIG if s['rs'] is not None):,}")
