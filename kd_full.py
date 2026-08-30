# -*- coding: utf-8 -*-
"""코스닥 1·2·3번 필터 최종 실측 (2021~2026) — 상장폐지 종목 포함
   생존 1,820종목 + 2021년 이후 코스닥 주권 보통주 폐지 128종목(스팩 제외)
   폐지 종목도 외국인·공매도 데이터를 갖췄으므로 실제 필터를 그대로 적용.
   청산: 보유 중 폐지되면 마지막 거래일 종가(정리매매)로 청산.
   거래대금: 1번 20억 / 2·3번 2억 (코스피와 같은 통과율) · 슬리피지 한 단계 상향
"""
import io, sqlite3, sys
from collections import defaultdict
import numpy as np, pandas as pd
import FinanceDataReader as fdr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
CASH = 3_000_000
AMT1, AMT2 = 20.0, 2.0

c = sqlite3.connect("file:data/kosdaq.db?mode=ro", uri=True, timeout=300)
SUR = pd.read_sql("""SELECT date,ticker,name,open,high,low,close,volume,frgn FROM daily
    WHERE close>0 AND open>0 ORDER BY ticker,date""", c); c.close()
DELT = set(pd.read_csv("data/kosdaq_delisted.csv", dtype=str).Symbol)
c = sqlite3.connect("file:data/delisted_kd.db?mode=ro", uri=True, timeout=300)
DEL = pd.read_sql("""SELECT date,ticker,name,open,high,low,close,volume,frgn FROM daily
    WHERE close>0 AND open>0 AND date>='20180101' ORDER BY ticker,date""", c); c.close()
DEL = DEL[DEL.ticker.isin(DELT) & ~DEL.ticker.isin(set(SUR.ticker))]
SUR["grp"], DEL["grp"] = "생존", "폐지"
print(f"생존 {SUR.ticker.nunique()}종목 {len(SUR):,}행 · 폐지 {DEL.ticker.nunique()}종목 {len(DEL):,}행")

df = pd.concat([SUR, DEL], ignore_index=True)
df = df[df.ticker.str.endswith("0")].sort_values(["ticker", "date"]).reset_index(drop=True)
dates = sorted(df.date.unique()); DI = {d: i for i, d in enumerate(dates)}
print(f"보통주 {df.ticker.nunique()}종목 · {len(df):,}행 · {dates[0]}~{dates[-1]}")

k = sqlite3.connect("file:data/kis/market.db?mode=ro", uri=True, timeout=300)
ss = pd.read_sql("SELECT date,ticker,short_ratio FROM short_sale WHERE short_ratio IS NOT NULL ORDER BY ticker,date", k); k.close()
ss = ss[ss.ticker.isin(set(df.ticker))]
gs = ss.groupby("ticker").short_ratio
ss["srd"] = gs.transform(lambda x: x.rolling(5).mean()) < gs.transform(lambda x: x.rolling(20).mean())
df = df.merge(ss[["date", "ticker", "srd"]], on=["date", "ticker"], how="left")
print(f"공매도 매칭 {df.srd.notna().sum():,}행")

d = sqlite3.connect("file:data/dart/disclosures.db?mode=ro", uri=True, timeout=300)
dz = pd.read_sql("""SELECT stock_code t, rcept_dt FROM disclosure WHERE
   replace(report_nm,' ','') LIKE '%유상증자결정%' OR replace(report_nm,' ','') LIKE '%전환사채권발행결정%'
   OR replace(report_nm,' ','') LIKE '%신주인수권부사채권발행결정%'""", d); d.close()
DIL = defaultdict(list)
for r in dz.itertuples(): DIL[r.t].append(r.rcept_dt)

IDX = {}
for tag, sym in (("KP", "KS11"), ("KQ", "KQ11")):
    ki = fdr.DataReader(sym, "2017-06-01"); ki = ki[ki.Close > 0]; ki.index = ki.index.strftime("%Y%m%d")
    kc = ki["Close"].reindex(dates).ffill()
    for w in (5, 20, 60):
        df[f"{tag}{w}"] = df.date.map(kc > kc.rolling(w).mean()).values
    df[f"{tag}ok"] = df.date.map(kc.rolling(60).mean().notna()).fillna(False).values

g = df.groupby("ticker", sort=False)
V, C = df.volume.astype(float), df.close
for w in (1, 3): df[f"vm{w}"] = g["volume"].transform(lambda x, w=w: x.rolling(w).mean())
df["a40"] = g["volume"].transform(lambda x: x.shift(3).rolling(40).mean())
df["a240"] = g["volume"].transform(lambda x: x.shift(43).rolling(240).mean())
df["r16"] = df.a40 / df.a240 * 100
df["rw1"] = df.vm3 / df.a40 * 100
df["su1"] = df.vm1 / g["volume"].transform(lambda x: x.shift(1).rolling(20).mean())
df["amt"] = (V * C).groupby(df.ticker).transform(lambda x: x.rolling(40).mean()).shift(3) / 1e8
df["amt20"] = (V * C).groupby(df.ticker).transform(lambda x: x.rolling(20).mean()) / 1e8
v5s = g["volume"].transform(lambda x: x.rolling(5).sum())
df["fw5"] = g["frgn"].transform(lambda x: x.fillna(0).rolling(5).sum()) / v5s.replace(0, np.nan) * 100
df["fw60"] = g["frgn"].transform(lambda x: x.fillna(0).rolling(60).sum()) / \
             g["volume"].transform(lambda x: x.rolling(60).sum()).replace(0, np.nan) * 100
for n in (3, 10, 20, 60): df[f"ret{n}"] = g.close.transform(lambda x, n=n: x / x.shift(n) - 1) * 100
op1 = g.open.shift(-1)
df["gap"] = (op1 / C - 1) * 100
df["y"] = df.date.str[:4].astype(int)
ds = pd.to_datetime(df.date); dil = np.zeros(len(df), bool)
for t, idx in df.groupby("ticker").indices.items():
    L = pd.to_datetime(DIL.get(t, []))
    if len(L) == 0: continue
    for i, x in zip(idx, ds.values[idx]):
        dil[i] = bool(((L.values >= x - np.timedelta64(90, "D")) & (L.values <= x)).any())
df["dil"] = dil
df["cost"] = 0.18 + np.select([df.amt20 >= 100, df.amt20 >= 50, df.amt20 >= 20, df.amt20 >= 10],
                              [.30, .50, .70, 1.00], default=1.50)
pc = g.close.shift(1); jj = (C / pc).where(pc > 0)
badday = ((jj > 1.32) | (jj < 0.68)).fillna(False)
bad = np.zeros(len(df), bool); pos = df.date.map(DI).values
for t, sub in df[badday].groupby("ticker"):
    idx = df.index[df.ticker == t].values
    bp = np.sort([DI[x] for x in sub.date if x in DI]); p = pos[idx]
    q = np.searchsorted(bp, p, side="right")
    bad[idx[(q < len(bp)) & (bp[np.minimum(q, len(bp) - 1)] - p <= 42)]] = True
print(f"불연속 인접 제외 {int(bad.sum()):,}행")

df["buy"] = op1
lastpos = g.date.transform("max").map(DI); lastclose = g.close.transform("last")
mypos = df.date.map(DI)
for h in (10, 20):
    sell = g.close.shift(-h)
    sell = sell.where(~(mypos + h > lastpos), lastclose)
    df[f"f{h}"] = (sell / df.buy - 1) * 100
hi10 = g.high.shift(-1).rolling(10, min_periods=1).max().shift(-9)
df["f10t"] = np.where(hi10 >= df.buy * 1.20, 20.0, df.f10)

import csv as _csv
IND = {r["ticker"]: r["industry"] for r in _csv.DictReader(open("data/industry.csv", encoding="utf-8")) if r.get("industry")}
df["up"] = df.ticker.map(IND)
_sa = df[df.up.notna() & df.ret60.notna()].groupby(["date","up"]).agg(sret60=("ret60","mean"), cnt=("ticker","size")).reset_index()
_sa = _sa[_sa.cnt >= 5]
df = df.merge(_sa[["date","up","sret60"]], on=["date","up"], how="left")
D = df[~bad & df.buy.notna() & df.KPok & df.KQok].copy().reset_index(drop=True)
print(f"평가 대상 {len(D):,}행 (폐지 {int((D.grp=='폐지').sum()):,}행)\n")

def build(tag):
    F1 = ((D.r16 < 50) & (D.rw1 >= 200) & (D.fw5 >= 3) & (D.amt >= AMT1)
          & D.ret10.between(0, 20) & (D[f"{tag}5"]==True) & (D[f"{tag}20"]==True) & (D.srd == True) & (D.gap < 5))
    F2 = ((D.r16 < 30) & (D.rw1 >= 200) & (D.fw5 >= 2) & (D.amt >= AMT2)
          & (D.ret3 <= -5) & (D.ret10 <= 0) & (D[f"{tag}20"]==False) & (D.srd == True) & (~D.dil))
    F3 = ((D.ret20 <= -20) & (D.su1 >= 2) & (D.fw60 >= 1) & (D.amt20 >= AMT2)
          & (D[f"{tag}60"]==False) & (D.srd == True) & (~D.dil))
    F3s = F3 & (D.sret60.isna() | (D.sret60 <= -15))          # 배포된 D1 = F3 + 업종 60일 -15%↓ (데이터 없으면 통과)
    return [("P1형 상승초입", F1, "f10t"), ("P2형 조정매집", F2, "f10"),
            ("D1 후보(업종조건 없음)", F3, "f20"), ("**D1 (배포본·업종 -15%)**", F3s, "f20")]

def trades(m, col):
    x = D[m.fillna(False)].copy(); x["r"] = x[col] - x.cost
    return x[np.isfinite(x.r)]

for tag, tn in (("KQ", "코스닥지수"), ("KP", "코스피지수")):
    SPEC = build(tag)
    print(f"\n## 시장 조건 = {tn} · 폐지 종목 포함\n")
    print("| 필터 | 신호 | 절대수익 | 중앙값 | 승률 | PF | 최악 | 폐지신호 | 학습(18~22) | 검증(23~26) | **300만원씩** |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    R = {}
    for lab, m, col in SPEC:
        t = trades(m, col); R[lab] = t; r = t.r.values
        if len(r) < 5: print(f"| {lab} | {len(r)} | 부족 |" + " - |" * 9); continue
        pf = r[r > 0].sum() / abs(r[r <= 0].sum()) if (r <= 0).any() else 99
        i_ = t[t.y <= 2022].r; o_ = t[t.y >= 2023].r
        print(f"| {lab} | {len(r)} | **{r.mean():+.2f}%** | {np.median(r):+.2f}% | {(r>0).mean()*100:.0f}% | {pf:.2f} | "
              f"{r.min():+.0f}% | {int((t.grp=='폐지').sum())}건 | {i_.mean():+.2f}% | **{o_.mean():+.2f}%** | "
              f"**{r.sum()/100*CASH/10000:+,.0f}만원** |")
    if tag == "KP":
        print(f"\n### 연도별 (코스피지수 기준 · 건수/평균/300만원 손익)\n")
        YS = list(range(2018, 2027))
        print("| 필터 | " + " | ".join(str(y) for y in YS) + " | 합계 |\n|---|" + "---|" * (len(YS) + 1))
        for lab, _, _ in SPEC:
            t = R[lab]
            if len(t) < 5: continue
            yy = t.groupby("y").r.agg(["size", "mean", "sum"])
            cells = [(f"**{yy.loc[y,'mean']:+.1f}%**<br>{int(yy.loc[y,'size'])}건<br>{yy.loc[y,'sum']/100*CASH/10000:+,.0f}만"
                      if y in yy.index else "-") for y in YS]
            print(f"| {lab} | " + " | ".join(cells) + f" | **{t.r.sum()/100*CASH/10000:+,.0f}만원** |")
        pd.concat([R[l].assign(F=l) for l, _, _ in SPEC]).to_csv("data/kd_full_trades.csv", index=False, encoding="utf-8-sig")
        dd = pd.concat([R[l].assign(F=l) for l, _, _ in SPEC])
        dd = dd[dd.grp == "폐지"]
        print(f"\n### 폐지 종목이 만든 거래 {len(dd)}건 (코스피지수 기준)\n")
        if len(dd):
            print("| 규칙 | 날짜 | 종목 | 수익 |\n|---|---|---|---|")
            for t in dd.nsmallest(10, "r").itertuples():
                print(f"| {t.F} | {t.date} | {t.name} | **{t.r:+.1f}%** |")
            print(f"\n폐지 종목 평균 **{dd.r.mean():+.2f}%** · 승률 {(dd.r>0).mean()*100:.0f}% · 최악 {dd.r.min():+.1f}%")
