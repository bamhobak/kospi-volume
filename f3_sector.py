# -*- coding: utf-8 -*-
"""3번 필터 + 업종 조건 — 실제 필터에 얹었을 때 성적이 어떻게 바뀌나
   기준: 생존 944 + 폐지 77 (보통주 891) · 2018~2026 · 다음날 시가 매수 · 20거래일 보유
"""
import io, sqlite3, sys, csv, time
from collections import defaultdict
import numpy as np, pandas as pd
import FinanceDataReader as fdr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
T0 = time.time()
def log(m): print(f"[{time.time()-T0:4.0f}s] {m}", flush=True)
CASH = 3_000_000

c = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True, timeout=300)
SUR = pd.read_sql("""SELECT date,ticker,name,open,high,low,close,volume,frgn FROM daily
    WHERE market='KOSPI' AND close>0 AND open>0 AND date>='20180101' ORDER BY ticker,date""", c); c.close()
c = sqlite3.connect("file:data/delisted.db?mode=ro", uri=True, timeout=300)
DEL = pd.read_sql("""SELECT date,ticker,name,open,high,low,close,volume,frgn FROM daily
    WHERE close>0 AND open>0 AND date>='20180101' ORDER BY ticker,date""", c); c.close()
DEL = DEL[~DEL.ticker.isin(set(SUR.ticker))]
SUR["grp"], DEL["grp"] = "생존", "폐지"
df = pd.concat([SUR, DEL], ignore_index=True)
df = df[df.ticker.str.endswith("0")].sort_values(["ticker", "date"]).reset_index(drop=True)
dates = sorted(df.date.unique()); DI = {d: i for i, d in enumerate(dates)}
log(f"{df.ticker.nunique()}종목 {len(df):,}행")

k = sqlite3.connect("file:data/kis/market.db?mode=ro", uri=True, timeout=300)
ss = pd.read_sql("SELECT date,ticker,short_ratio FROM short_sale WHERE short_ratio IS NOT NULL ORDER BY ticker,date", k); k.close()
ss = ss[ss.ticker.isin(set(df.ticker))]
gs = ss.groupby("ticker").short_ratio
ss["srd"] = gs.transform(lambda x: x.rolling(5).mean()) < gs.transform(lambda x: x.rolling(20).mean())
df = df.merge(ss[["date", "ticker", "srd"]], on=["date", "ticker"], how="left")
d = sqlite3.connect("file:data/dart/disclosures.db?mode=ro", uri=True, timeout=300)
dz = pd.read_sql("""SELECT stock_code t, rcept_dt FROM disclosure WHERE
   replace(report_nm,' ','') LIKE '%유상증자결정%' OR replace(report_nm,' ','') LIKE '%전환사채권발행결정%'
   OR replace(report_nm,' ','') LIKE '%신주인수권부사채권발행결정%'""", d); d.close()
DIL = defaultdict(list)
for r in dz.itertuples(): DIL[r.t].append(r.rcept_dt)

ki = fdr.DataReader("KS11", "2016-06-01"); ki = ki[ki.Close > 0]; ki.index = ki.index.strftime("%Y%m%d")
kc = ki["Close"].reindex(dates).ffill()
for w in (20, 60): df[f"K{w}"] = df.date.map(kc > kc.rolling(w).mean()).fillna(False).values

g = df.groupby("ticker", sort=False)
V, C = df.volume.astype(float), df.close
df["vm1"] = V
df["su1"] = V / g["volume"].transform(lambda x: x.shift(1).rolling(20).mean())
df["amt20"] = (V * C).groupby(df.ticker).transform(lambda x: x.rolling(20).mean()) / 1e8
df["fw60"] = g["frgn"].transform(lambda x: x.fillna(0).rolling(60).sum()) / \
             g["volume"].transform(lambda x: x.rolling(60).sum()).replace(0, np.nan) * 100
for n in (20, 60): df[f"ret{n}"] = g.close.transform(lambda x, n=n: x / x.shift(n) - 1) * 100
op1 = g.open.shift(-1)
df["y"] = df.date.str[:4].astype(int)
ds = pd.to_datetime(df.date); dil = np.zeros(len(df), bool)
for t, idx in df.groupby("ticker").indices.items():
    L = pd.to_datetime(DIL.get(t, []))
    if len(L) == 0: continue
    for i, x in zip(idx, ds.values[idx]):
        dil[i] = bool(((L.values >= x - np.timedelta64(90, "D")) & (L.values <= x)).any())
df["dil"] = dil
df["cost"] = 0.18 + np.select([df.amt20 >= 100, df.amt20 >= 50, df.amt20 >= 20, df.amt20 >= 10],
                              [.20, .30, .50, .70], default=1.00)
pc = g.close.shift(1); jj = (C / pc).where(pc > 0)
badday = ((jj > 1.32) | (jj < 0.68)).fillna(False)
bad = np.zeros(len(df), bool); pos = df.date.map(DI).values
for t, sub in df[badday].groupby("ticker"):
    idx = df.index[df.ticker == t].values
    bp = np.sort([DI[x] for x in sub.date if x in DI]); p = pos[idx]
    q = np.searchsorted(bp, p, side="right")
    bad[idx[(q < len(bp)) & (bp[np.minimum(q, len(bp) - 1)] - p <= 42)]] = True
df["buy"] = op1
lastpos = g.date.transform("max").map(DI); lastclose = g.close.transform("last"); mypos = df.date.map(DI)
sell = g.close.shift(-20)
df["f20"] = (sell.where(~(mypos + 20 > lastpos), lastclose) / df.buy - 1) * 100

# ── 업종 ─────────────────────────────────────────────────────
UP = {r["ticker"]: r["gname"] for r in csv.DictReader(open("data/sector.csv", encoding="utf-8"))
      if r["kind"] == "upjong"}
# 폐지 종목은 KRX 폐지목록의 Industry 로 보완
try:
    kd = fdr.StockListing("KRX-DELISTING")
    for r in kd.itertuples():
        if isinstance(r.Symbol, str) and r.Symbol not in UP and isinstance(r.Industry, str) and r.Industry:
            UP[r.Symbol] = "폐지:" + r.Industry[:12]
except Exception as e: log(f"폐지 업종 보완 실패: {str(e)[:50]}")
df["up"] = df.ticker.map(UP)
log(f"업종 매핑 {df[df.up.notna()].ticker.nunique()}/{df.ticker.nunique()}종목")

# 업종 60일 수익률 (동일가중, 회원 5종목 이상) — 업종명이 '폐지:'로 시작하는 건 집계에서 제외
agg_src = df[df.up.notna() & ~df.up.str.startswith("폐지:").fillna(False) & df.ret60.notna()]
sa = agg_src.groupby(["date", "up"]).agg(sret60=("ret60", "mean"), sret20=("ret20", "mean"),
                                         cnt=("ticker", "size")).reset_index()
sa = sa[sa.cnt >= 5]
df = df.merge(sa[["date", "up", "sret60", "sret20"]], on=["date", "up"], how="left")
log(f"업종-일자 {len(sa):,}건 · 업종수익 매칭 {df.sret60.notna().sum():,}행")

D = df[~bad & df.buy.notna() & df.f20.notna()].reset_index(drop=True)
log(f"평가 {len(D):,}행")

# ── 3번 필터 (현행) ──────────────────────────────────────────
F3 = ((D.ret20 <= -20) & (D.su1 >= 2) & (D.fw60 >= 1) & (D.amt20 >= 3)
      & (~D.K60) & (D.srd == True) & (~D.dil))
log(f"3번 필터 신호 {int(F3.sum())}건 · 업종수익 있는 신호 {int((F3 & D.sret60.notna()).sum())}건")

def ev(m):
    x = D[m.fillna(False)]
    r = (x.f20 - x.cost).values; y = x.y.values
    ok = np.isfinite(r); r, y, x = r[ok], y[ok], x[ok]
    if len(r) < 10: return None
    rs = np.sort(r); yy = pd.Series(r).groupby(y).agg(["mean", "size"]); yy = yy[yy["size"] >= 3]
    return dict(n=len(r), ret=r.mean(), med=np.median(r), win=(r > 0).mean()*100,
                pf=(r[r>0].sum()/abs(r[r<=0].sum())) if (r<=0).any() else 99.,
                is_=r[y <= 2022].mean(), os_=r[y >= 2023].mean(),
                t5=rs[:-5].mean() if len(rs) > 5 else np.nan, worst=r.min(),
                pos=int((yy["mean"] > 0).sum()), ny=len(yy), tot=r.sum()/100*CASH, r=r, y=y)
HDR = ("| 조건 | 신호 | 절대수익 | 중앙값 | 승률 | PF | 상위5제외 | 학습(~22) | 검증(23~) | +연도 | 최악 | 300만씩 |\n"
       "|---|---|---|---|---|---|---|---|---|---|---|---|")
def row(lab, m):
    s = ev(m)
    if not s: return print(f"| {lab} | {int(m.fillna(False).sum())} | 10건 미만 |" + " - |" * 10)
    print(f"| {lab} | {s['n']} | **{s['ret']:+.2f}%** | {s['med']:+.2f}% | {s['win']:.0f}% | {s['pf']:.2f} | "
          f"{s['t5']:+.2f}% | {s['is_']:+.2f}% | **{s['os_']:+.2f}%** | {s['pos']}/{s['ny']} | {s['worst']:+.0f}% | "
          f"**{s['tot']/10000:+,.0f}만** |")

HAS = D.sret60.notna()
print("\n## ① 업종 조건 추가 (20거래일 보유)\n"); print(HDR)
row("**현행 3번 필터**", F3)
row("현행 3번 · 업종수익 계산 가능한 신호만 (비교 기준)", F3 & HAS)
for th in (0, -5, -10, -15, -20, -25, -30):
    row(f"+ 업종 60일 {th}% 이하", F3 & HAS & (D.sret60 <= th))
print("\n(참고) 반대 방향")
row("+ 업종 60일 0% 이상 (업종은 멀쩡)", F3 & HAS & (D.sret60 > 0))

print("\n## ② 업종 20일 수익률로 하면\n"); print(HDR)
for th in (0, -5, -10, -15):
    row(f"+ 업종 20일 {th}% 이하", F3 & HAS & (D.sret20 <= th))

print("\n## ③ 종목이 업종보다 더 빠졌나 (상대 낙폭)\n"); print(HDR)
D["rel60"] = D.ret60 - D.sret60
for lab, m in [("종목이 업종보다 더 하락(rel<0)", D.rel60 < 0),
               ("종목이 업종보다 10%p↑ 더 하락", D.rel60 <= -10),
               ("종목이 업종보다 20%p↑ 더 하락", D.rel60 <= -20),
               ("종목이 업종보다 덜 하락(rel>0)", D.rel60 > 0)]:
    row(lab, F3 & HAS & m)

BEST = F3 & HAS & (D.sret60 <= -20)
print("\n## ④ 연도별 비교 (300만원씩)\n")
YS = list(range(2018, 2027))
print("| 조건 | " + " | ".join(str(y) for y in YS) + " | 합계 |\n|---|" + "---|" * (len(YS) + 1))
for lab, m in (("현행 3번", F3), ("+ 업종 60일 -20%↓", BEST)):
    s = ev(m); yy = pd.Series(s["r"]).groupby(s["y"]).agg(["mean", "size", "sum"])
    cells = [(f"**{yy.loc[y,'mean']:+.1f}%**<br>{int(yy.loc[y,'size'])}건" if y in yy.index else "-") for y in YS]
    print(f"| {lab} | " + " | ".join(cells) + f" | **{s['tot']/10000:+,.0f}만** |")

print("\n## ⑤ 신호 빈도\n")
for lab, m in (("현행 3번", F3), ("+ 업종 -20%↓", BEST)):
    x = D[m.fillna(False)]
    ym = x.date.str[:6].nunique()
    print(f"- {lab}: {len(x)}건 / 104개월 · 신호 있는 달 {ym}개월({ym/104*100:.0f}%) · 월평균 {len(x)/104:.1f}건")
log("완료")
