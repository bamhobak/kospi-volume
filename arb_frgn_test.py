# -*- coding: utf-8 -*-
"""매수차익거래(현물 저평가 → 프로그램이 현물 매수) × 외국인 보유 증감 다각도 실측.

'저가로 평가된 상품을 매수' = 매수차익거래(현물 매수 + 선물 매도). 종목 관점에서는 arb_net > 0.
  ⚠ 선물 가격·괴리율 데이터는 없다. arb_net 부호를 대리 지표로 쓴다(정직하게 밝혀 둔다).
외국인 보유: kospi.db/kosdaq.db 의 foreign_ratio(지분율, 2005~) 로 변화폭과 방향을 만든다.

축
  pa5/pa20/pa60 : 5·20·60일 누적 차익 순매수 / 같은 기간 거래량 ×100  (매수차익 강도)
  abr           : 20일 차익 매수 / (매수+매도)  — 0.5 초과면 매수 우위
  fd5/fd20/fd60 : 외국인 지분율 5·20·60일 변화폭(%p)
  frr           : 지분율 20일평균 / 250일평균
사용: python arb_frgn_test.py
"""
import sqlite3, warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from techlib import *

c = sqlite3.connect(f"file:{BASE}/data/toss.db?mode=ro", uri=True)
P = pd.read_sql("SELECT date,ticker,arb_buy,arb_sell,arb_net,narb_net FROM program", c); c.close()
F = []
for db in ("kospi.db", "kosdaq.db"):
    k = sqlite3.connect(f"file:{BASE}/data/{db}?mode=ro", uri=True)
    F.append(pd.read_sql("SELECT date,ticker,foreign_ratio fr FROM daily "
                         "WHERE date>='20170101' AND foreign_ratio IS NOT NULL", k)); k.close()
F = pd.concat(F).drop_duplicates(["ticker","date"])
X = P.merge(F, on=["date","ticker"], how="outer").merge(
        A[["date","ticker","volume"]], on=["date","ticker"], how="left").sort_values(["ticker","date"])
gX = X.groupby("ticker", sort=False)
rs = lambda col, n: gX[col].transform(lambda s: s.rolling(n, min_periods=max(3, n*3//4)).sum())
z = lambda s: s.replace(0, np.nan)
for n in (5, 20, 60):
    X[f"pa{n}"] = rs("arb_net", n) / z(rs("volume", n)) * 100
X["pn20"] = rs("narb_net", 20) / z(rs("volume", 20)) * 100
X["abr"]  = rs("arb_buy", 20) / z(rs("arb_buy", 20) + rs("arb_sell", 20))
X["pshare"] = (rs("arb_buy",20)+rs("arb_sell",20)) / z(rs("volume",20)) * 100   # 차익거래가 거래량에서 차지하는 비중
for n in (5, 20, 60):
    X[f"fd{n}"] = X.fr - gX.fr.shift(n)
X["fr20m"] = gX.fr.transform(lambda s: s.rolling(20, min_periods=15).mean())
X["fr250m"] = gX.fr.transform(lambda s: s.rolling(250, min_periods=180).mean())
X["frr"] = X.fr20m / z(X.fr250m)
keep = ["date","ticker","pa5","pa20","pa60","pn20","abr","pshare","fd5","fd20","fd60","frr","fr"]
n0 = len(A); T = A.merge(X[keep], on=["ticker","date"], how="left"); assert len(T) == n0
for k in keep[2:]: A[k] = T[k].values
del T, X, P, F
for h in (15, 30): A[f"n{h}"] = (g.close.shift(-h)/A.buy - 1)*100 - A.cost
ok = A.pa20.notna() & A.fd20.notna()
print(f"두 축이 다 있는 행 {int(ok.sum()):,} · 기간 {A.loc[ok,'date'].min()}~{A.loc[ok,'date'].max()} "
      f"· 종목 {A.loc[ok,'ticker'].nunique():,} · 2023년 이후 {A.loc[ok,'date'].ge('20230101').mean():.0%}")
print(f"차익 순매수>0 비율 {(A.pa20>0).mean():.0%} · 외인 지분율 20일 증가 비율 {(A.fd20>0).mean():.0%}\n")
HOLDS = (5, 10, 20, 40, 60)
def blk(t, cond, mk=None, reg=None, minn=30, holds=HOLDS):
    print(f"── {t}"); hdr()
    for h in holds: go(f"  {h}일", cond, hold=h, mk=mk, reg=reg, minn=minn)
    print()

BUY = A.pa20 > 0.3          # 매수차익 우위
FUP = A.fd20 > 0            # 외인 지분율 증가
print("■ 1) 네 조합 · 보유기간별")
blk("차익매수(pa20>0.3) + 외인 증가", BUY & FUP)
blk("차익매수(pa20>0.3) + 외인 감소", BUY & ~FUP)
blk("차익매도(pa20<-0.3) + 외인 증가", (A.pa20 < -0.3) & FUP)
blk("차익매도(pa20<-0.3) + 외인 감소", (A.pa20 < -0.3) & ~FUP)

print("■ 2) 차익매수 강도 × 외인 증가폭 격자 (20일)"); hdr()
for p in (0.1, 0.3, 0.5, 1.0, 2.0):
    for f_ in (0, 0.1, 0.3, 0.5):
        go(f"  pa20>{p} · 외인20 +{f_}%p↑", (A.pa20 > p) & (A.fd20 > f_), hold=20, minn=30)
print()
print("■ 2b) 차익매수 × 외인 감소폭 격자 (20일)"); hdr()
for p in (0.3, 0.5, 1.0, 2.0):
    for f_ in (0, -0.1, -0.3, -0.5):
        go(f"  pa20>{p} · 외인20 {f_}%p↓", (A.pa20 > p) & (A.fd20 < f_), hold=20, minn=30)
print()

print("■ 3) 차익 기간 바꾸기 (외인 증가 고정 · 20일)"); hdr()
for col, nm in (("pa5","5일"), ("pa20","20일"), ("pa60","60일")):
    for p in (0.3, 1.0):
        go(f"  차익 {nm} >{p} · 외인↑", (A[col] > p) & FUP, hold=20, minn=30)
print()
print("■ 4) 외인 기간 바꾸기 (차익매수 고정 · 20일)"); hdr()
for col, nm in (("fd5","5일"), ("fd20","20일"), ("fd60","60일")):
    go(f"  외인 {nm} 증가 · 차익매수", BUY & (A[col] > 0), hold=20, minn=30)
    go(f"  외인 {nm} 감소 · 차익매수", BUY & (A[col] < 0), hold=20, minn=30)
go("  외인 1년대비 20일 ↑(frr>1.05) · 차익매수", BUY & (A.frr > 1.05), hold=20, minn=30)
go("  외인 1년대비 20일 ↓(frr<0.95) · 차익매수", BUY & (A.frr < 0.95), hold=20, minn=30)
print()

print("■ 5) 매수 우위 비율(abr)·차익 비중(pshare) 로 보기 (20일)"); hdr()
for a in (0.55, 0.6, 0.7):
    go(f"  abr>{a} (매수 우위) · 외인↑", (A.abr > a) & FUP, hold=20, minn=30)
    go(f"  abr>{a} (매수 우위) · 외인↓", (A.abr > a) & ~FUP, hold=20, minn=30)
for s in (1, 3, 5):
    go(f"  차익비중 pshare>{s}% · 차익매수 · 외인↑", (A.pshare > s) & BUY & FUP, hold=20, minn=30)
print()

print("■ 6) 각 축 단독 — 조합이 기여하나 (20일)"); hdr()
for p in (0.3, 1.0, 2.0): go(f"  차익매수 pa20>{p} 단독", A.pa20 > p, hold=20, minn=30)
go("  외인 20일 증가 단독", FUP, hold=20, minn=30)
go("  외인 20일 감소 단독", ~FUP, hold=20, minn=30)
go("  외인 20일 +0.5%p↑ 단독", A.fd20 > 0.5, hold=20, minn=30)
print()

print("■ 7) 시장·국면 (차익매수 + 외인 증가 · 20일)"); hdr()
for mk in ("KOSPI", "KOSDAQ"): go(f"  {mk}", BUY & FUP, hold=20, mk=mk, minn=25)
for rg in ("UP", "SIDE", "DN"): go(f"  {rg}", BUY & FUP, hold=20, reg=rg, minn=25)
print()

print("■ 8) 우리 재료 얹기 (차익매수 + 외인 증가 · 20일)"); hdr()
go("  + 60일선 위", BUY & FUP & (A.dma60 > 0), hold=20, minn=30)
go("  + 20일 낙폭 -10% 이하", BUY & FUP & (A.ret20 <= -10), hold=20, minn=30)
go("  + 고점 -15% 이내", BUY & FUP & (A.fromhi >= -15), hold=20, minn=30)
go("  + 거래대금 100억↑", BUY & FUP & (A.amt20 >= 100), hold=20, minn=30)
go("  + 시총 1조↑", BUY & FUP & (A.marcap >= 1e4), hold=20, minn=30)
go("  + 공매도 감소(sr20≤0)", BUY & FUP & (A.sr20 <= 0), hold=20, minn=30)
go("  + 비차익도 순매수(pn20>0)", BUY & FUP & (A.pn20 > 0), hold=20, minn=30)
go("  + 비차익은 순매도(pn20<0)", BUY & FUP & (A.pn20 < 0), hold=20, minn=30)
print()

for nm, cond in (("차익매수+외인 증가", BUY & FUP), ("차익매수+외인 감소", BUY & ~FUP)):
    Y = go("", cond, hold=20, minn=1, quiet=True)
    if len(Y):
        yr = Y.groupby("yr").agg(n=("r","size"), avg=("r","mean"), med=("r","median"),
                                 win=("r", lambda s: (s>0).mean()*100), al=("alpha","mean"))
        print(f"■ 연도별 ({nm} · 20일)")
        for y, r in yr.iterrows():
            print(f"   {y}  {int(r.n):>5}건  평균 {r.avg:>+6.2f}%  중앙 {r.med:>+5.1f}  승률 {r.win:>3.0f}%  초과 {r.al:>+5.2f}")
        print(f"   최다 연도 {Y.yr.value_counts(normalize=True).max():.0%} · 신호 난 달 {Y.ym.nunique()}개월 · 종목 {Y.ticker.nunique()}개\n")
