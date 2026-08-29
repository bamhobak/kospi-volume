# -*- coding: utf-8 -*-
"""절대수익 관점 재평가 — 특히 하락 구간 성과 (dedup 없음 = 실전 동일)"""
import io, pickle, sqlite3, sys
from collections import defaultdict
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
SRD = defaultdict(dict)
for r in ss.itertuples(): SRD[r.ticker][r.date] = bool(np.isfinite(r.sr5) and np.isfinite(r.sr20) and r.sr5 < r.sr20)
d = sqlite3.connect("file:data/dart/disclosures.db?mode=ro", uri=True)
dz = pd.read_sql("""SELECT stock_code AS t, rcept_dt FROM disclosure
  WHERE replace(report_nm,' ','') LIKE '%유상증자결정%' OR replace(report_nm,' ','') LIKE '%전환사채권발행결정%'
     OR replace(report_nm,' ','') LIKE '%신주인수권부사채권발행결정%'""", d); d.close()
DIL = defaultdict(list)
for r in dz.itertuples(): DIL[r.t].append(r.rcept_dt)
ki = fdr.DataReader("KS11", "2017-12-01"); ki = ki[ki.Close > 0]; ki.index = ki.index.strftime("%Y%m%d")
KO = ki["Open"].reindex(dates).ffill().values; KC = ki["Close"].reindex(dates).ffill().values
K20 = (ki["Close"] > ki["Close"].rolling(20).mean()).reindex(dates).ffill().fillna(False).values
K60 = (ki["Close"] > ki["Close"].rolling(60).mean()).reindex(dates).ffill().fillna(False).values
ND = len(dates)
MKT = np.full(ND, np.nan)
for p in range(ND - H - 2):
    o = KO[p + 1]
    if np.isfinite(o) and o > 0: MKT[p] = (KC[p + 1 + H] / o - 1) * 100
def cost(a): return 0.18 + (0.20 if a >= 100 else 0.30 if a >= 50 else 0.50 if a >= 20 else 0.70 if a >= 10 else 1.00)

R = []
for t, g in df.groupby("ticker", sort=False):
    if not t.endswith("0") or len(g) < 400: continue
    g = g.reset_index(drop=True); n = len(g)
    O, Hh, L, C = (g[c].values.astype(float) for c in ("open", "high", "low", "close"))
    V = g.volume.values.astype(float); F = np.nan_to_num(g.frgn.values.astype(float)); D = g.date.values
    S = pd.Series
    a1 = S(V).shift(3).rolling(40).mean().values; a6 = S(V).shift(43).rolling(240).mean().values
    aw = S(V).rolling(3).mean().values
    amt = (S(V * C).shift(3).rolling(40).mean() / 1e8).values
    v5 = S(V).rolling(5).sum().values; f5 = S(F).rolling(5).sum().values
    with np.errstate(invalid="ignore", divide="ignore"):
        quiet = a1 / a6; surge = aw / a1; fwp = f5 / v5 * 100
        ret3 = (C / np.roll(C, 3) - 1) * 100; ret10 = (C / np.roll(C, 10) - 1) * 100
    ret3[:3] = np.nan; ret10[:10] = np.nan
    gn = T2G.get(t)
    rs = np.array([RS[gn].get(x, np.nan) for x in D]) if (gn and gn != "기타" and gn in RS.columns) else np.full(n, np.nan)
    gp = np.array([POS.get(x, -1) for x in D])
    dl = pd.to_datetime(DIL.get(t, [])) if DIL.get(t) else None
    ds = pd.to_datetime(D)
    for j in range(n - H - 2):
        if gp[j] < 0 or not np.isfinite(quiet[j]) or not np.isfinite(surge[j]) or not np.isfinite(amt[j]): continue
        if surge[j] < 2 or not np.isfinite(fwp[j]) or fwp[j] < 2: continue
        o0 = O[j + 1]
        if not np.isfinite(o0) or o0 <= 0 or not np.isfinite(MKT[gp[j]]): continue
        c_ = cost(amt[j])
        r1 = None
        for kk in range(H + 1):
            lo = (L[j+1+kk]/o0-1)*100; hi = (Hh[j+1+kk]/o0-1)*100
            if lo <= -15: r1 = -15 - c_; break
            if hi >= 30: r1 = 30 - c_; break
            if kk == H: r1 = (C[j+1+kk]/o0-1)*100 - c_
        r2 = (C[j+1+H]/o0-1)*100 - c_
        dil = bool(dl is not None and ((dl >= ds[j] - pd.Timedelta(days=90)) & (dl <= ds[j])).any())
        R.append(dict(t=t, d=D[j], y=int(D[j][:4]), mk=MKT[gp[j]], r1=r1, r2=r2,
                      quiet=quiet[j], amt=amt[j], ret3=ret3[j], ret10=ret10[j],
                      k20=bool(K20[gp[j]]), k60=bool(K60[gp[j]]),
                      rs=rs[j], srd=SRD[t].get(D[j], False), dil=dil))
P = pd.DataFrame(R)
print(f"후보 풀 {len(P):,}건 (급등2배·외인2%)")
P["f1"] = (P.quiet < 0.5) & (P.amt >= 50) & (P.ret10.between(0, 20)) & P.k20 & P.rs.notna() & (P.rs > 0)
P.to_pickle("data/pool_abs.pkl")
P["f2"] = (P.quiet < 0.3) & (P.amt >= 3) & (P.ret3 <= 0) & P.srd & (~P.dil)
def stat(d, col):
    if len(d) < 10: return None
    r = d[col]
    return dict(n=len(r), ret=r.mean(), med=r.median(), win=(r > 0).mean()*100,
                pf=(r[r>0].sum()/abs(r[r<=0].sum())) if (r<=0).any() else 99)
print("\n## 절대수익 — 시장 국면별 (보유 10일 동안 코스피 등락 기준)\n")
print("| 필터 | 구간 | 건수 | 절대수익 | 중앙값 | 승률 | PF | 같은구간 지수 |\n|---|---|---|---|---|---|---|---|")
for fn, col, lab in (("f1", "r1", "1번"), ("f2", "r2", "2번")):
    d = P[P[fn]]
    for seg, m in (("전체", d.index == d.index), ("지수 상승", d.mk > 0), ("**지수 하락**", d.mk <= 0),
                   ("지수 -3% 이하", d.mk <= -3)):
        s = stat(d[m], col)
        if s: print(f"| {lab} | {seg} | {s['n']} | **{s['ret']:+.2f}%** | {s['med']:+.2f}% | {s['win']:.0f}% | {s['pf']:.2f} | {d[m].mk.mean():+.2f}% |")
print("\n## 연도별 절대수익\n")
print("| 필터 | " + " | ".join(str(y) for y in range(2019, 2027)) + " |\n|---|" + "---|"*8)
for fn, col, lab in (("f1", "r1", "1번"), ("f2", "r2", "2번")):
    d = P[P[fn]]
    cells = []
    for y in range(2019, 2027):
        g2 = d[d.y == y]
        cells.append(f"{g2[col].mean():+.1f}({len(g2)})" if len(g2) >= 3 else "-")
    print(f"| {lab} | " + " | ".join(cells) + " |")
kc = ki["Close"].copy(); kc.index = pd.to_datetime(kc.index)
ky = kc.resample("YE").last().pct_change() * 100
print("| 코스피 | " + " | ".join(f"{ky[ky.index.year==y].iloc[0]:+.0f}%" if (ky.index.year==y).any() else "-" for y in range(2019,2027)) + " |")
print("\n## 2번 필터 — 하락 구간에서 성과를 살리는 조건 (지수 하락 구간만, n>=15)\n")
d = P[P.f2 & (P.mk <= 0)]
print(f"하락 구간 신호 {len(d)}건 · 기준 {d.r2.mean():+.2f}%\n")
print("| 추가 조건 | 건수 | 절대수익 | 중앙값 | 승률 | PF |\n|---|---|---|---|---|---|")
CONDS = [("없음", d.index == d.index), ("코스피 20일선 위", d.k20), ("코스피 20일선 아래", ~d.k20),
         ("코스피 60일선 아래", ~d.k60), ("잠잠<0.2", d.quiet < 0.2), ("잠잠<0.15", d.quiet < 0.15),
         ("대금 10억↑", d.amt >= 10), ("대금 30억↑", d.amt >= 30),
         ("3일 -5% 이하 급락", d.ret3 <= -5), ("3일 -10% 이하", d.ret3 <= -10),
         ("10일도 하락", d.ret10 <= 0), ("업종 상대강도>0", d.rs > 0), ("업종 상대강도<0", d.rs < 0)]
for lab, m in CONDS:
    s = stat(d[m], "r2")
    if s and s["n"] >= 15: print(f"| {lab} | {s['n']} | **{s['ret']:+.2f}%** | {s['med']:+.2f}% | {s['win']:.0f}% | {s['pf']:.2f} |")
