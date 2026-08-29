# -*- coding: utf-8 -*-
"""1번 필터 탐색용 확장 풀 생성 — 피처 다수 + 40일 가격경로 저장"""
import io, pickle, sqlite3, sys
from collections import defaultdict
import numpy as np, pandas as pd
import FinanceDataReader as fdr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
NB = 41
con = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True)
df = pd.read_sql("""SELECT date,ticker,close,volume,frgn,organ,open,high,low FROM daily
   WHERE market='KOSPI' AND close IS NOT NULL AND open>0 ORDER BY ticker,date""", con)
sec = pd.read_sql("SELECT ticker,gname FROM sector WHERE kind='upjong'", con)
dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily ORDER BY date")]; con.close()
POS = {d: i for i, d in enumerate(dates)}; T2G = dict(sec.values)
RS = pickle.load(open("data/sector_index.pkl", "rb"))["upjong"]["rs20"]
k = sqlite3.connect("file:data/kis/market.db?mode=ro", uri=True)
ss = pd.read_sql("SELECT date,ticker,short_ratio FROM short_sale WHERE short_ratio IS NOT NULL", k); k.close()
ss = ss.sort_values(["ticker", "date"]); gg = ss.groupby("ticker")["short_ratio"]
ss["sr5"] = gg.transform(lambda x: x.rolling(5).mean()); ss["sr20"] = gg.transform(lambda x: x.rolling(20).mean())
SR = defaultdict(dict)
for r in ss.itertuples(): SR[r.ticker][r.date] = (r.sr5, r.sr20)
d = sqlite3.connect("file:data/dart/disclosures.db?mode=ro", uri=True)
dz = pd.read_sql("""SELECT stock_code AS t, rcept_dt FROM disclosure
  WHERE replace(report_nm,' ','') LIKE '%유상증자결정%' OR replace(report_nm,' ','') LIKE '%전환사채권발행결정%'
     OR replace(report_nm,' ','') LIKE '%신주인수권부사채권발행결정%'""", d); d.close()
DIL = defaultdict(list)
for r in dz.itertuples(): DIL[r.t].append(r.rcept_dt)
ki = fdr.DataReader("KS11", "2017-12-01"); ki = ki[ki.Close > 0]; ki.index = ki.index.strftime("%Y%m%d")
KO = ki["Open"].reindex(dates).ffill().values; KC = ki["Close"].reindex(dates).ffill().values
K20 = (ki["Close"] > ki["Close"].rolling(20).mean()).reindex(dates).ffill().fillna(False).values
K5 = (ki["Close"] > ki["Close"].rolling(5).mean()).reindex(dates).ffill().fillna(False).values
ND = len(dates)
MKT = np.full((ND, NB), np.nan)      # 지수 수익 (매수일 시가 → k일 뒤 종가)
for p in range(ND - NB - 2):
    o = KO[p + 1]
    if np.isfinite(o) and o > 0:
        MKT[p, :] = (KC[p+1:p+1+NB] / o - 1) * 100

ROWS = []; PATH_H = []; PATH_L = []; PATH_C = []
for t, g in df.groupby("ticker", sort=False):
    if not t.endswith("0") or len(g) < 400: continue
    g = g.reset_index(drop=True); n = len(g)
    O, Hh, L, C = (g[c].values.astype(float) for c in ("open", "high", "low", "close"))
    V = g.volume.values.astype(float)
    F = np.nan_to_num(g.frgn.values.astype(float)); R = np.nan_to_num(g.organ.values.astype(float))
    D = g.date.values; S = pd.Series
    a1 = S(V).shift(3).rolling(40).mean().values; a6 = S(V).shift(43).rolling(240).mean().values
    aw = S(V).rolling(3).mean().values
    amt = (S(V * C).shift(3).rolling(40).mean() / 1e8).values
    v5 = S(V).rolling(5).sum().values; f5 = S(F).rolling(5).sum().values; r5 = S(R).rolling(5).sum().values
    v20 = S(V).rolling(20).sum().values; f20 = S(F).rolling(20).sum().values
    ma20 = S(C).rolling(20).mean().values; ma60 = S(C).rolling(60).mean().values
    hi52 = S(Hh).rolling(240).max().values
    vol20 = (S(C).pct_change().rolling(20).std() * 100).values
    with np.errstate(invalid="ignore", divide="ignore"):
        quiet = a1 / a6; surge = aw / a1
        fwp = f5 / v5 * 100; owp = r5 / v5 * 100; fwp20 = f20 / v20 * 100
        ret3 = (C / np.roll(C, 3) - 1) * 100; ret5 = (C / np.roll(C, 5) - 1) * 100
        ret10 = (C / np.roll(C, 10) - 1) * 100; ret20 = (C / np.roll(C, 20) - 1) * 100
        dev20 = (C / ma20 - 1) * 100; dev60 = (C / ma60 - 1) * 100; nearhi = (C / hi52 - 1) * 100
    for a_ in (ret3, ret5, ret10, ret20): a_[:20] = np.nan
    gn = T2G.get(t)
    rs = np.array([RS[gn].get(x, np.nan) for x in D]) if (gn and gn != "기타" and gn in RS.columns) else np.full(n, np.nan)
    gp = np.array([POS.get(x, -1) for x in D])
    dl = pd.to_datetime(DIL.get(t, [])) if DIL.get(t) else None
    ds = pd.to_datetime(D)
    for j in range(n - NB - 2):
        if gp[j] < 0 or not np.isfinite(quiet[j]) or not np.isfinite(surge[j]) or not np.isfinite(amt[j]): continue
        if surge[j] < 2 or not np.isfinite(fwp[j]) or fwp[j] < 2: continue      # 공통 골격
        o0 = O[j + 1]
        if not np.isfinite(o0) or o0 <= 0 or not np.isfinite(MKT[gp[j], 10]): continue
        s5, s20 = SR[t].get(D[j], (np.nan, np.nan))
        dil = bool(dl is not None and ((dl >= ds[j] - pd.Timedelta(days=90)) & (dl <= ds[j])).any())
        ROWS.append((t, D[j], int(D[j][:4]), gp[j], amt[j], quiet[j], surge[j], fwp[j], fwp20[j], owp[j],
                     ret3[j], ret5[j], ret10[j], ret20[j], dev20[j], dev60[j], nearhi[j], vol20[j],
                     rs[j], s5, s20, bool(K20[gp[j]]), bool(K5[gp[j]]), dil))
        PATH_H.append((Hh[j+1:j+1+NB] / o0 - 1) * 100)
        PATH_L.append((L[j+1:j+1+NB] / o0 - 1) * 100)
        PATH_C.append((C[j+1:j+1+NB] / o0 - 1) * 100)
COLS = ["t", "d", "y", "gp", "amt", "quiet", "surge", "fwp", "fwp20", "owp", "ret3", "ret5", "ret10", "ret20",
        "dev20", "dev60", "nearhi", "vol20", "rs", "sr5", "sr20", "k20", "k5", "dil"]
P = pd.DataFrame(ROWS, columns=COLS)
np.save("data/p1_H.npy", np.array(PATH_H, dtype=np.float32))
np.save("data/p1_L.npy", np.array(PATH_L, dtype=np.float32))
np.save("data/p1_C.npy", np.array(PATH_C, dtype=np.float32))
np.save("data/p1_MKT.npy", MKT.astype(np.float32))
P.to_pickle("data/p1.pkl")
print(f"풀 {len(P):,}건 · {P.d.min()}~{P.d.max()} · {P.t.nunique()}종목")
print("연도별:", P.y.value_counts().sort_index().to_dict())
