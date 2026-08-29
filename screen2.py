# -*- coding: utf-8 -*-
"""지표 스크리닝 v2 — 벤치마크 = 동일가중 평균(실제로 살 수 있는 대안)"""
import io, pickle, sqlite3, sys
import numpy as np, pandas as pd
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HOR = [5, 10, 20, 60]
con = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True)
df = pd.read_sql("""SELECT date,ticker,close,volume,frgn,organ,open,high,low FROM daily
   WHERE market='KOSPI' AND close IS NOT NULL AND open>0 ORDER BY ticker,date""", con)
sec = pd.read_sql("SELECT ticker,gname FROM sector WHERE kind='upjong'", con); con.close()
k = sqlite3.connect("file:data/kis/market.db?mode=ro", uri=True)
ss = pd.read_sql("SELECT date,ticker,short_ratio FROM short_sale WHERE short_ratio IS NOT NULL", k); k.close()
df = df.merge(ss, on=["date", "ticker"], how="left")
Z = pickle.load(open("data/sector_index.pkl", "rb"))
RS = Z["upjong"]["rs20"].stack().rename("rs").reset_index(); RS.columns = ["date", "gname", "rs"]
df = df.merge(sec, on="ticker", how="left").merge(RS, on=["date", "gname"], how="left")
g = df.groupby("ticker", sort=False)
rl = lambda c, n, f="mean": g[c].transform(lambda x: getattr(x.rolling(n), f)())
df["quiet"]   = rl("volume", 40) / g["volume"].transform(lambda x: x.shift(40).rolling(200).mean())
df["surge"]   = rl("volume", 5) / rl("volume", 60)
df["amt"]     = (df.volume * df.close).groupby(df.ticker).transform(lambda x: x.rolling(20).mean()) / 1e8
df["amtsurge"]= (df.volume * df.close).groupby(df.ticker).transform(lambda x: x.rolling(5).mean() / x.rolling(60).mean())
for n in (5, 20, 60, 120):
    df[f"ret{n}"] = g["close"].transform(lambda x, n=n: x / x.shift(n) - 1) * 100
    df[f"ma{n}"]  = df.close / rl("close", n) - 1
df["vol20"]   = g["close"].transform(lambda x: x.pct_change().rolling(20).std()) * 100
df["volchg"]  = g["close"].transform(lambda x: x.pct_change().rolling(5).std()) / g["close"].transform(lambda x: x.pct_change().rolling(60).std())
df["hi52"]    = df.close / g["high"].transform(lambda x: x.rolling(240).max()) - 1
df["lo52"]    = df.close / g["low"].transform(lambda x: x.rolling(240).min()) - 1
df["gap"]     = df.open / g["close"].transform(lambda x: x.shift(1)) - 1
v5, v20 = rl("volume", 5, "sum"), rl("volume", 20, "sum")
df["fw5"]  = g["frgn"].transform(lambda x: x.fillna(0).rolling(5).sum()) / v5 * 100
df["fw20"] = g["frgn"].transform(lambda x: x.fillna(0).rolling(20).sum()) / v20 * 100
df["fw60"] = g["frgn"].transform(lambda x: x.fillna(0).rolling(60).sum()) / rl("volume", 60, "sum") * 100
df["ow20"] = g["organ"].transform(lambda x: x.fillna(0).rolling(20).sum()) / v20 * 100
df["fo20"] = df.fw20 + df.ow20
df["fstreak"] = g["frgn"].transform(lambda x: (x.fillna(0) > 0).rolling(10).sum())
df["sr20"]  = rl("short_ratio", 20)
df["srchg"] = rl("short_ratio", 5) - rl("short_ratio", 20)
df["pref"]  = ~df.ticker.str.endswith("0")
op = g["open"].transform(lambda x: x.shift(-1))
for h in HOR:
    raw = ((g["close"].transform(lambda x, h=h: x.shift(-h)) / op - 1) * 100).replace([np.inf, -np.inf], np.nan)
    raw = raw.where(raw.abs() < 200)
    df[f"f{h}"] = raw - df.assign(r=raw).groupby("date")["r"].transform("mean")
df["y"] = df.date.str[:4].astype(int)
S = df[(df.amt >= 10) & (~df.pref) & df.f10.notna()].copy(); S = S[S.index % 5 == 0]
print(f"분석 {len(S):,}행 · {S.date.min()}~{S.date.max()} · 벤치마크=동일가중 평균\n")
FEAT = [("quiet","잠잠도(낮을수록)",True),("surge","거래량급등(5/60)",False),("amtsurge","거래대금급등",False),
        ("ret5","5일수익",False),("ret20","20일수익",False),("ret60","60일수익",False),("ret120","120일수익",False),
        ("ma20","20일선이격",False),("ma60","60일선이격",False),("ma120","120일선이격",False),
        ("vol20","20일변동성",True),("volchg","변동성축소(5/60)",True),
        ("hi52","52주고가대비",False),("lo52","52주저가대비",True),("gap","시가갭",False),
        ("amt","거래대금",False),("fw5","외국인5일",False),("fw20","외국인20일",False),("fw60","외국인60일",False),
        ("ow20","기관20일",False),("fo20","외국인+기관20일",False),("fstreak","외국인 순매수일수",False),
        ("sr20","공매도비중20일",False),("srchg","공매도 5일-20일",True),("rs","업종상대강도",False)]
rows = []
for f, lab, asc in FEAT:
    d = S[S[f].notna() & np.isfinite(S[f])]
    if len(d) < 20000: continue
    r = d.groupby("date")[f].rank(pct=True, ascending=asc)
    top = d[r <= 0.20]; bot = d[r > 0.80]
    e = {}
    for h in HOR:
        t = top.groupby("y")[f"f{h}"].mean(); b = bot.groupby("y")[f"f{h}"].mean()
        e[h] = (t.mean(), (t > 0).sum(), len(t), b.mean())
    rows.append((lab, len(d), e))
print("## 상위 20% 그룹의 초과수익 (동일가중 대비) · (플러스 연도/전체)\n")
print("| 지표 | 샘플 | " + " | ".join(f"{h}일" for h in HOR) + " |")
print("|---|---|" + "---|" * len(HOR))
for lab, n, e in sorted(rows, key=lambda x: -x[2][20][0]):
    cs = []
    for h in HOR:
        v, p, t, b = e[h]
        cs.append(f"**{v:+.2f}** ({p}/{t})" if v > 0.2 and p >= t - 1 else f"{v:+.2f} ({p}/{t})")
    print(f"| {lab} | {n:,} | " + " | ".join(cs) + " |")
print("\n## 하위 20% 그룹 (피해야 할 종목) · 20일 기준\n")
print("| 지표 | 하위20% 초과수익 | 상위20% | 차이 |\n|---|---|---|---|")
for lab, n, e in sorted(rows, key=lambda x: x[2][20][3]):
    v, p, t, b = e[20]
    print(f"| {lab} | **{b:+.2f}%** | {v:+.2f}% | {v-b:+.2f}%p |")
