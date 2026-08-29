# -*- coding: utf-8 -*-
"""공매도 회피 전략 — 미래참조 제거판 (선택은 전일 정보, 보유는 다음날부터)"""
import io, sqlite3, sys
import numpy as np, pandas as pd
import FinanceDataReader as fdr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
con = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True)
df = pd.read_sql("""SELECT date,ticker,close,volume,open FROM daily
   WHERE market='KOSPI' AND close IS NOT NULL AND open>0 ORDER BY ticker,date""", con); con.close()
k = sqlite3.connect("file:data/kis/market.db?mode=ro", uri=True)
ss = pd.read_sql("SELECT date,ticker,short_ratio FROM short_sale WHERE short_ratio IS NOT NULL", k); k.close()
df = df.merge(ss, on=["date", "ticker"], how="left")
g = df.groupby("ticker", sort=False)
df["dret"] = g["close"].transform(lambda x: x.pct_change()) * 100
df["sr20"] = g["short_ratio"].transform(lambda x: x.rolling(20).mean())
df["amt"]  = (df.volume * df.close).groupby(df.ticker).transform(lambda x: x.rolling(20).mean()) / 1e8
U = df[df.ticker.str.endswith("0")].copy()
dates = sorted(U.date.unique())
RET = U.pivot_table(index="date", columns="ticker", values="dret", aggfunc="first").reindex(dates)
SR  = U.pivot_table(index="date", columns="ticker", values="sr20", aggfunc="first").reindex(index=dates, columns=RET.columns)
AMT = U.pivot_table(index="date", columns="ticker", values="amt", aggfunc="first").reindex(index=dates, columns=RET.columns)
# ★ 선택 정보는 모두 1일 지연 (전일 종가까지 알 수 있는 정보만 사용)
SRl, AMTl = SR.shift(1), AMT.shift(1)
ELIG = (AMTl >= 10) & RET.notna()
PSR = SRl.where(ELIG).rank(axis=1, pct=True)
BAN = [("20200316", "20210502"), ("20231106", "20250330")]
banset = {d for d in dates for a, b in BAN if a <= d <= b}
COSTR = 0.18 + np.select([AMTl >= 100, AMTl >= 50, AMTl >= 20, AMTl >= 10], [0.20, 0.30, 0.50, 0.70], default=1.00)
COSTR = pd.DataFrame(COSTR, index=dates, columns=RET.columns)

def run(sel_mask, reb, lab):
    keep = (ELIG & sel_mask).astype(float)
    rebd = set(dates[::reb]); cur = None; W = []; cost = []
    for d in dates:
        if cur is None or d in rebd:
            t = keep.loc[d]; s = t.sum()
            new = t / s if s > 0 else t
            c = 0.0 if cur is None else float(((new - cur).abs() / 2 * COSTR.loc[d].fillna(1.0)).sum())
            cur = new; cost.append(c)
        else:
            cur = cur * (1 + RET.loc[d].fillna(0) / 100); cur = cur / cur.sum()
            cost.append(0.0)
        W.append(cur.copy())
    w = pd.DataFrame(W, index=dates)
    pr = (w.shift(1).fillna(0) * RET.fillna(0)).sum(axis=1) - pd.Series(cost, index=dates)
    pr = pr.iloc[1:]
    cum = (1 + pr / 100).cumprod(); dd = (cum / cum.cummax() - 1) * 100
    yrs = len(pr) / 246
    nb = pr[~pr.index.isin(banset)]; cn = (1 + nb / 100).cumprod()
    yr = {}
    for y in range(2019, 2027):
        c = cum[cum.index.str[:4] == str(y)]
        yr[y] = (c.iloc[-1] / c.iloc[0] - 1) * 100 if len(c) > 5 else None
    return dict(lab=lab, cagr=(cum.iloc[-1]**(1/yrs)-1)*100, cagrn=(cn.iloc[-1]**(246/len(nb))-1)*100,
                mdd=dd.min(), sh=pr.mean()/pr.std()*np.sqrt(246),
                cost=sum(cost)/yrs, n=keep.sum(axis=1).mean(), yr=yr)
ki = fdr.DataReader("KS11", "2018-01-01"); ki = ki[ki.Close > 0]; ki.index = ki.index.strftime("%Y%m%d")
b = ki.Close.reindex(dates).ffill(); cb = b / b.iloc[0]
ddb = (cb / cb.cummax() - 1) * 100
prb = b.pct_change().dropna() * 100
print("## 미래참조 제거 후 (선택 정보 1일 지연 · 비용 반영 · 대금 10억↑)\n")
print("| 전략 | 리밸런싱 | CAGR | CAGR(정상기간) | MDD | 샤프 | 연비용 | 종목 |")
print("|---|---|---|---|---|---|---|---|")
print(f"| 코스피 지수 | - | {(cb.iloc[-1]**(246/len(dates))-1)*100:+.1f}% | - | {ddb.min():.1f}% | {prb.mean()/prb.std()*np.sqrt(246):.2f} | - | - |")
T = ELIG & ELIG
for reb in (20, 60, 120):
    r = run(T, reb, "동일가중")
    print(f"| 동일가중 전종목 | {reb}일 | {r['cagr']:+.1f}% | {r['cagrn']:+.1f}% | {r['mdd']:.1f}% | {r['sh']:.2f} | {r['cost']:.1f}% | {r['n']:.0f} |")
for pct in (0.5, 0.7):
    for reb in (20, 60, 120):
        r = run(PSR <= pct, reb, f"공매도 하위{int(pct*100)}%")
        print(f"| **공매도 하위{int(pct*100)}%** | {reb}일 | **{r['cagr']:+.1f}%** | **{r['cagrn']:+.1f}%** | {r['mdd']:.1f}% | {r['sh']:.2f} | {r['cost']:.1f}% | {r['n']:.0f} |")
print("\n## 연도별 (60일 리밸런싱)\n| 전략 | " + " | ".join(str(y) for y in range(2019, 2027)) + " |\n|---|" + "---|"*8)
for lab, m in [("동일가중 전종목", T), ("공매도 하위50%", PSR <= 0.5), ("공매도 하위70%", PSR <= 0.7)]:
    r = run(m, 60, lab)
    print(f"| {lab} | " + " | ".join(f"{v:+.0f}%" if v is not None else "-" for v in r["yr"].values()) + " |")
