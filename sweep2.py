# -*- coding: utf-8 -*-
"""2번 필터 윈도우 재스윕 — dedup 없음(실전 동일) · 학습(2019~2022)/검증(2023~2026) 분리
   전체 조건: 잠잠<TH · 급등>=2배 · 외국인5일>=2% · 대금>=3억 · 3일 하락 · 공매도 감소 · 유상증자90일 없음
"""
import io, pickle, sqlite3, sys
from collections import defaultdict
import numpy as np, pandas as pd
import FinanceDataReader as fdr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
WB = [120, 180, 240, 360, 480, 660]
WQ = [20, 30, 40, 60, 90]
WS = [1, 2, 3, 5, 10]
TH = [0.2, 0.3, 0.4, 0.5]
H = 10
ALLW = sorted(set(WB + WQ + WS))
con = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True)
df = pd.read_sql("""SELECT date,ticker,close,volume,frgn,open,high,low FROM daily
   WHERE market='KOSPI' AND close IS NOT NULL AND open>0 ORDER BY ticker,date""", con)
dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily ORDER BY date")]; con.close()
POS = {d: i for i, d in enumerate(dates)}
k = sqlite3.connect("file:data/kis/market.db?mode=ro", uri=True)
ss = pd.read_sql("SELECT date,ticker,short_ratio FROM short_sale WHERE short_ratio IS NOT NULL", k); k.close()
ss = ss.sort_values(["ticker", "date"]); gg = ss.groupby("ticker")["short_ratio"]
ss["sr5"] = gg.transform(lambda x: x.rolling(5).mean()); ss["sr20"] = gg.transform(lambda x: x.rolling(20).mean())
SRD = defaultdict(dict)
for r in ss.itertuples():
    SRD[r.ticker][r.date] = bool(np.isfinite(r.sr5) and np.isfinite(r.sr20) and r.sr5 < r.sr20)
d = sqlite3.connect("file:data/dart/disclosures.db?mode=ro", uri=True)
dz = pd.read_sql("""SELECT stock_code AS t, rcept_dt FROM disclosure
  WHERE replace(report_nm,' ','') LIKE '%유상증자결정%' OR replace(report_nm,' ','') LIKE '%전환사채권발행결정%'
     OR replace(report_nm,' ','') LIKE '%신주인수권부사채권발행결정%'""", d); d.close()
DIL = defaultdict(list)
for r in dz.itertuples(): DIL[r.t].append(r.rcept_dt)
ki = fdr.DataReader("KS11", "2017-12-01"); ki = ki[ki.Close > 0]; ki.index = ki.index.strftime("%Y%m%d")
KO = ki["Open"].reindex(dates).ffill().values; KC = ki["Close"].reindex(dates).ffill().values
ND = len(dates)
MKT = np.full(ND, np.nan)
for p in range(ND - H - 2):
    o = KO[p + 1]
    if np.isfinite(o) and o > 0: MKT[p] = (KC[p + 1 + H] / o - 1) * 100
def rmean(a, w):
    c = np.concatenate(([0.0], np.cumsum(np.nan_to_num(a))))
    out = np.full(len(a), np.nan); out[w-1:] = (c[w:] - c[:-w]) / w
    return out
def cost(a): return 0.18 + (0.20 if a >= 100 else 0.30 if a >= 50 else 0.50 if a >= 20 else 0.70 if a >= 10 else 1.00)
COMBO = [(b, q, s, th) for b in WB for q in WQ for s in WS for th in TH]
CIX = {c: i for i, c in enumerate(COMBO)}
YEARS = list(range(2019, 2027)); YIX = {y: i for i, y in enumerate(YEARS)}
ACC = np.zeros((len(COMBO), len(YEARS), 3))     # n, sum_alpha, n_alpha_pos

for t, g in df.groupby("ticker", sort=False):
    if not t.endswith("0") or len(g) < 700: continue
    g = g.reset_index(drop=True); n = len(g)
    O, C = g.open.values.astype(float), g.close.values.astype(float)
    V = g.volume.values.astype(float); F = np.nan_to_num(g.frgn.values.astype(float)); D = g.date.values
    gp = np.array([POS.get(x, -1) for x in D])
    VM = {w: rmean(V, w) for w in ALLW}; AM = {w: rmean(V * C, w) for w in WQ}
    v5 = pd.Series(V).rolling(5).sum().values; f5 = pd.Series(F).rolling(5).sum().values
    with np.errstate(invalid="ignore", divide="ignore"):
        fwp = f5 / v5 * 100
        ret3 = (C / np.roll(C, 3) - 1) * 100
    ret3[:3] = np.nan
    srd = np.array([SRD[t].get(x, False) for x in D])
    dl = DIL.get(t, [])
    if dl:
        ds = pd.to_datetime(D); dil = np.zeros(n, bool)
        dlts = pd.to_datetime(dl)
        for i in range(n):
            lo = ds[i] - pd.Timedelta(days=90)
            dil[i] = bool(((dlts >= lo) & (dlts <= ds[i])).any())
    else:
        dil = np.zeros(n, bool)
    ret_ex = np.full(n, np.nan)
    valid = np.zeros(n, bool)
    for j in range(n - H - 2):
        o0 = O[j + 1]
        if np.isfinite(o0) and o0 > 0:
            ret_ex[j] = (C[j + 1 + H] / o0 - 1) * 100
            valid[j] = True
    yr = np.array([int(x[:4]) for x in D])
    base = valid & np.isfinite(fwp) & np.isfinite(ret3) & (gp >= 0) & (fwp >= 2) & (ret3 <= 0) & srd & (~dil)
    if not base.any(): continue
    mk = np.where(gp >= 0, MKT[np.clip(gp, 0, ND - 1)], np.nan)
    for b in WB:
        for q in WQ:
            for s in WS:
                vq = np.roll(VM[q], s); vq[:s] = np.nan
                vb = np.roll(VM[b], s + q); vb[:s+q] = np.nan
                aq = np.roll(AM[q], s) / 1e8; aq[:s] = np.nan
                with np.errstate(invalid="ignore", divide="ignore"):
                    quiet = vq / vb; surge = VM[s] / vq
                ok = base & np.isfinite(quiet) & np.isfinite(surge) & np.isfinite(aq) & (surge >= 2) & (aq >= 3) & np.isfinite(mk)
                if not ok.any(): continue
                c_ = np.array([cost(x) if np.isfinite(x) else 1.0 for x in aq])
                al = (ret_ex - c_) - mk
                for th in TH:
                    m = ok & (quiet < th)
                    idx = np.where(m)[0]
                    if len(idx) == 0: continue
                    ci = CIX[(b, q, s, th)]
                    for j in idx:
                        y = yr[j]
                        if y in YIX:
                            ACC[ci, YIX[y]] += (1, al[j], 1 if al[j] > 0 else 0)

np.save("data/sweep2.npy", ACC)
IS = [YIX[y] for y in (2019, 2020, 2021, 2022)]
OS = [YIX[y] for y in (2023, 2024, 2025, 2026)]
rows = []
for c, ci in CIX.items():
    a = ACC[ci]
    n_all = a[:, 0].sum()
    if n_all < 60: continue
    nis, nos = a[IS, 0].sum(), a[OS, 0].sum()
    if nis < 20 or nos < 20: continue
    yal = np.divide(a[:, 1], a[:, 0], out=np.zeros(len(YEARS)), where=a[:, 0] >= 3)
    pos = int(((yal > 0) & (a[:, 0] >= 3)).sum()); tot = int((a[:, 0] >= 3).sum())
    rows.append(dict(c=c, n=int(n_all), al=a[:, 1].sum()/n_all, alw=a[:, 2].sum()/n_all*100,
                     is_=a[IS, 1].sum()/nis, os_=a[OS, 1].sum()/nos, nis=int(nis), nos=int(nos), pos=f"{pos}/{tot}"))
M = {120: "6개월", 180: "9개월", 240: "1년", 360: "1.5년", 480: "2년", 660: "2년9개월"}
Q = {20: "1개월", 30: "45일", 40: "2개월", 60: "3개월", 90: "4.5개월"}
lab = lambda c: f"기준{M[c[0]]}·잠잠{Q[c[1]]}<{c[3]}·급등{c[2]}일"
cur = [r for r in rows if r["c"] == (240, 40, 3, 0.3)]
print(f"조합 {len(rows)}개 (건수 60↑ · 학습/검증 각 20건↑)\n")
print("## 현행 설정\n")
print("| 설정 | 건수 | 전체 초과 | 초과승률 | 학습(19~22) | 검증(23~26) | 초과+ 연도 |\n|---|---|---|---|---|---|---|")
for r in cur:
    print(f"| {lab(r['c'])} | {r['n']} | **{r['al']:+.2f}%** | {r['alw']:.0f}% | {r['is_']:+.2f}% ({r['nis']}) | **{r['os_']:+.2f}%** ({r['nos']}) | {r['pos']} |")
print("\n## 학습기간(2019~2022) 상위 10 → 검증기간 성적\n")
print("| 설정 | 건수 | 학습(19~22) | **검증(23~26)** | 전체 | 초과승률 | 초과+ 연도 |\n|---|---|---|---|---|---|---|")
for r in sorted(rows, key=lambda x: -x["is_"])[:10]:
    print(f"| {lab(r['c'])} | {r['n']} | {r['is_']:+.2f}% ({r['nis']}) | **{r['os_']:+.2f}%** ({r['nos']}) | {r['al']:+.2f}% | {r['alw']:.0f}% | {r['pos']} |")
print("\n## 양 기간 모두 플러스인 조합 (검증 성적순 상위 12)\n")
both = [r for r in rows if r["is_"] > 0 and r["os_"] > 0]
print(f"총 {len(both)}개 / {len(rows)}개\n")
print("| 설정 | 건수 | 학습 | **검증** | 전체 | 초과승률 | 초과+ 연도 |\n|---|---|---|---|---|---|---|")
for r in sorted(both, key=lambda x: -x["os_"])[:12]:
    print(f"| {lab(r['c'])} | {r['n']} | {r['is_']:+.2f}% | **{r['os_']:+.2f}%** | {r['al']:+.2f}% | {r['alw']:.0f}% | {r['pos']} |")
