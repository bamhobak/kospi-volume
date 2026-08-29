# -*- coding: utf-8 -*-
"""중복 제거(MINGAP) 방식이 성과에 미치는 영향 — 1·2번 필터 현행 조건 고정"""
import io, pickle, sqlite3, sys
import numpy as np, pandas as pd
import FinanceDataReader as fdr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
H = 10
con = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True)
df = pd.read_sql("""SELECT date,ticker,close,volume,frgn,open,high,low FROM daily
   WHERE market='KOSPI' AND close IS NOT NULL AND open>0 ORDER BY ticker,date""", con)
sec = pd.read_sql("SELECT ticker,gname FROM sector WHERE kind='upjong'", con)
dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily ORDER BY date")]; con.close()
POS = {d: i for i, d in enumerate(dates)}; T2G = dict(sec.values)
RS = pickle.load(open("data/sector_index.pkl", "rb"))["upjong"]["rs20"]
k = sqlite3.connect("file:data/kis/market.db?mode=ro", uri=True)
ss = pd.read_sql("SELECT date,ticker,short_ratio FROM short_sale WHERE short_ratio IS NOT NULL", k); k.close()
ss = ss.sort_values(["ticker", "date"]); gg = ss.groupby("ticker")["short_ratio"]
ss["sr5"] = gg.transform(lambda x: x.rolling(5).mean()); ss["sr20"] = gg.transform(lambda x: x.rolling(20).mean())
SRD = {(r.date, r.ticker): bool(np.isfinite(r.sr5) and np.isfinite(r.sr20) and r.sr5 < r.sr20) for r in ss.itertuples()}
d = sqlite3.connect("file:data/dart/disclosures.db?mode=ro", uri=True)
dz = pd.read_sql("""SELECT stock_code AS t, rcept_dt FROM disclosure
  WHERE replace(report_nm,' ','') LIKE '%유상증자결정%' OR replace(report_nm,' ','') LIKE '%전환사채권발행결정%'
     OR replace(report_nm,' ','') LIKE '%신주인수권부사채권발행결정%'""", d); d.close()
from collections import defaultdict
DIL = defaultdict(list)
for r in dz.itertuples(): DIL[r.t].append(r.rcept_dt)
ki = fdr.DataReader("KS11", "2017-12-01"); ki = ki[ki.Close > 0]; ki.index = ki.index.strftime("%Y%m%d")
KO = ki["Open"].reindex(dates).ffill().values; KC = ki["Close"].reindex(dates).ffill().values
K20 = (ki["Close"] > ki["Close"].rolling(20).mean()).reindex(dates).ffill().fillna(False).values
ND = len(dates)
IDX = np.full((ND, H + 1), np.nan)
for p in range(ND - H - 2):
    o = KO[p + 1]
    if np.isfinite(o) and o > 0:
        for kk in range(H + 1): IDX[p, kk] = (KC[p + 1 + kk] / o - 1) * 100
def cost(a): return 0.18 + (0.20 if a >= 100 else 0.30 if a >= 50 else 0.50 if a >= 20 else 0.70 if a >= 10 else 1.00)

REC = {1: [], 2: []}
for t, g in df.groupby("ticker", sort=False):
    if not t.endswith("0") or len(g) < 400: continue
    g = g.reset_index(drop=True); n = len(g)
    O, Hh, L, C = (g[c].values.astype(float) for c in ("open", "high", "low", "close"))
    V = g.volume.values.astype(float); F = np.nan_to_num(g.frgn.values.astype(float)); D = g.date.values
    S = pd.Series
    aw3 = S(V).rolling(3).mean().values
    a1 = S(V).shift(3).rolling(40).mean().values
    a6 = S(V).shift(43).rolling(240).mean().values
    amt = (S(V * C).shift(3).rolling(40).mean() / 1e8).values
    v5 = S(V).rolling(5).sum().values; f5 = S(F).rolling(5).sum().values
    with np.errstate(invalid="ignore", divide="ignore"):
        quiet = a1 / a6; surge = aw3 / a1; fwp = f5 / v5 * 100
        ret3 = (C / np.roll(C, 3) - 1) * 100; ret10 = (C / np.roll(C, 10) - 1) * 100
    ret3[:3] = np.nan; ret10[:10] = np.nan
    gn = T2G.get(t)
    rs = np.array([RS[gn].get(x, np.nan) for x in D]) if (gn and gn != "기타" and gn in RS.columns) else np.full(n, np.nan)
    gp = np.array([POS.get(x, -1) for x in D])
    for j in range(n - H - 2):
        if gp[j] < 0 or not np.isfinite(quiet[j]) or not np.isfinite(surge[j]): continue
        if surge[j] < 2 or quiet[j] > 0.7: continue          # 넓은 후보 풀 (구버전 dedup 기준)
        o0 = O[j + 1]
        if not np.isfinite(o0) or o0 <= 0: continue
        c_ = cost(amt[j] if np.isfinite(amt[j]) else 3)
        r1 = None
        for kk in range(H + 1):
            lo = (L[j+1+kk]/o0-1)*100; hi = (Hh[j+1+kk]/o0-1)*100
            if lo <= -15: r1 = (-15-c_, kk); break
            if hi >= 30: r1 = (30-c_, kk); break
            if kk == H: r1 = ((C[j+1+kk]/o0-1)*100-c_, kk)
        r2 = ((C[j+1+H]/o0-1)*100-c_, H)
        base = np.isfinite(fwp[j]) and np.isfinite(ret3[j]) and np.isfinite(ret10[j]) and np.isfinite(amt[j])
        p1 = bool(base and quiet[j] < 0.5 and fwp[j] >= 2 and amt[j] >= 50 and 0 <= ret10[j] <= 20
                  and K20[gp[j]] and np.isfinite(rs[j]) and rs[j] > 0)
        dd = D[j]
        lo90 = (pd.Timestamp(dd) - pd.Timedelta(days=90)).strftime("%Y%m%d")
        dil = any(lo90 <= x <= dd for x in DIL.get(t, []))
        p2 = bool(base and quiet[j] < 0.3 and fwp[j] >= 2 and amt[j] >= 3 and ret3[j] <= 0
                  and SRD.get((dd, t), False) and not dil)
        rec = dict(t=t, j=j, y=int(dd[:4]), p=gp[j], pass1=p1, pass2=p2,
                   r1=r1[0], k1=r1[1], r2=r2[0], k2=r2[1])
        REC[1].append(rec)
    REC[2] = REC[1]
pool = REC[1]
print(f"넓은 후보 풀 {len(pool):,}건 · 1번 통과 {sum(x['pass1'] for x in pool):,} · 2번 통과 {sum(x['pass2'] for x in pool):,}")

def evaluate(fi, mode):
    key_pass, key_r, key_k = f"pass{fi}", f"r{fi}", f"k{fi}"
    out = []
    bylast = {}
    if mode == "pool":       # 넓은 풀 기준 15일 dedup 후 필터 (구버전 = sig_2018.pkl)
        for x in pool:
            lt = bylast.get(x["t"], -99)
            if x["j"] - lt < 15: continue
            bylast[x["t"]] = x["j"]
            if x[key_pass]: out.append(x)
    elif mode == "filter":   # 필터 통과분끼리만 15일 dedup
        for x in pool:
            if not x[key_pass]: continue
            lt = bylast.get(x["t"], -99)
            if x["j"] - lt < 15: continue
            bylast[x["t"]] = x["j"]; out.append(x)
    else:                    # dedup 없음 (실전 = 매일 조건 맞으면 전부)
        out = [x for x in pool if x[key_pass]]
    rows = []
    for x in out:
        mk = IDX[x["p"], x[key_k]]
        if not np.isfinite(mk): continue
        rows.append((x["y"], x[key_r], x[key_r] - mk))
    dd = pd.DataFrame(rows, columns=["y", "ret", "al"])
    yy = dd.groupby("y").al.mean(); cnt = dd.groupby("y").size(); ok = yy[cnt >= 3]
    return dict(n=len(dd), ret=dd.ret.mean(), al=dd.al.mean(), med=dd.al.median(),
                win=(dd.ret > 0).mean()*100, alw=(dd.al > 0).mean()*100, pos=f"{(ok>0).sum()}/{len(ok)}", yy=yy, cnt=cnt)
print("\n## 중복 제거 방식별 성과 (조건은 현행 그대로)\n")
print("| 필터 | dedup 방식 | 건수 | 절대수익 | **초과수익** | 초과중앙값 | 승률 | 초과승률 | 초과+ 연도 |")
print("|---|---|---|---|---|---|---|---|---|")
res = {}
for fi in (1, 2):
    for mode, lab in (("pool", "넓은 풀 15일 (기존 보고값)"), ("filter", "필터 통과분 15일"), ("none", "**없음 (실전)**")):
        a = evaluate(fi, mode); res[(fi, mode)] = a
        print(f"| {fi}번 | {lab} | {a['n']} | {a['ret']:+.2f}% | **{a['al']:+.2f}%** | {a['med']:+.2f}% | {a['win']:.0f}% | {a['alw']:.0f}% | {a['pos']} |")
print("\n## dedup 없음(실전) 연도별\n")
print("| 필터 | " + " | ".join(str(y) for y in range(2019, 2027)) + " |\n|---|" + "---|" * 8)
for fi in (1, 2):
    a = res[(fi, "none")]
    print(f"| {fi}번 | " + " | ".join(
        f"{a['yy'].get(y, float('nan')):+.1f}({a['cnt'].get(y,0)})" if y in a["yy"] else "-" for y in range(2019, 2027)) + " |")
