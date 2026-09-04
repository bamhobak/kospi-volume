# -*- coding: utf-8 -*-
"""신용잔고 비율(융자잔고율)의 '중기 급감 → 단기 급증' 과 그 반대를 다각도로 실측.

원안  : 최근 3개월 평균 / 1년 평균 < 0.5 (50%↑ 감소)  AND  최근 1주 평균 / 3개월 평균 > 1.5 (50%↑ 증가)
반대안: 최근 3개월 평균 / 1년 평균 > 1.5              AND  최근 1주 평균 / 3개월 평균 < 0.5
자료: data/kis/market.db credit.loan_rmnd_rate (2018-01~2026-08, 일 1,300~1,450종목 — 신용거래 가능 종목만)
판단: techlib 게이트(학습CI>0·붐제외CI>0·중앙>0·붐제외중앙>0·상위5%제거>0) + 유니버스 대비 초과.
"""
import sqlite3, warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from techlib import *

c = sqlite3.connect(f"file:{BASE}/data/kis/market.db?mode=ro", uri=True, timeout=600)
C = pd.read_sql("SELECT date,ticker,loan_rmnd_rate rate,loan_rmnd qty FROM credit "
                "WHERE loan_rmnd_rate IS NOT NULL", c); c.close()
C = C.sort_values(["ticker","date"]); gC = C.groupby("ticker", sort=False)
C["cr5"]   = gC.rate.transform(lambda s: s.rolling(5,   min_periods=4).mean())
C["cr20"]  = gC.rate.transform(lambda s: s.rolling(20,  min_periods=15).mean())
C["cr60"]  = gC.rate.transform(lambda s: s.rolling(60,  min_periods=45).mean())
C["cr40"]  = gC.rate.transform(lambda s: s.rolling(40,  min_periods=30).mean())
C["cr80"]  = gC.rate.transform(lambda s: s.rolling(80,  min_periods=60).mean())
C["cr3"]   = gC.rate.transform(lambda s: s.rolling(3,   min_periods=2).mean())
C["cr10"]  = gC.rate.transform(lambda s: s.rolling(10,  min_periods=7).mean())
C["cr250"] = gC.rate.transform(lambda s: s.rolling(250, min_periods=180).mean())
z = lambda s: s.replace(0, np.nan)
C["drop"]  = C.cr60 / z(C.cr250)      # 중기(3개월) / 장기(1년)
C["rise"]  = C.cr5  / z(C.cr60)       # 단기(1주)  / 중기(3개월)
C["drop40"]= C.cr40 / z(C.cr250)      # 3개월 창 변형
C["drop80"]= C.cr80 / z(C.cr250)
C["rise3"] = C.cr3  / z(C.cr60)       # 1주 창 변형
C["rise10"]= C.cr10 / z(C.cr60)
C["risem"] = C.cr20 / z(C.cr60)       # 1개월 / 3개월
keep = ["date","ticker","rate","drop","rise","drop40","drop80","rise3","rise10","risem","cr250"]
n0 = len(A); T = A.merge(C[keep], on=["ticker","date"], how="left"); assert len(T) == n0
for k in keep[2:]: A[k] = T[k].values
del T, C
for h in (15, 30): A[f"n{h}"] = (g.close.shift(-h)/A.buy - 1)*100 - A.cost
ok = A["drop"].notna() & A["rise"].notna()
print(f"두 비율이 다 있는 행 {int(ok.sum()):,} · 기간 {A.loc[ok,'date'].min()}~{A.loc[ok,'date'].max()} "
      f"· 종목 {A.loc[ok,'ticker'].nunique():,} · 2023년 이후 {A.loc[ok,'date'].ge('20230101').mean():.0%}\n")

HOLDS = (5, 10, 20, 40, 60)
def blk(t, cond, mk=None, reg=None, minn=30, holds=HOLDS):
    print(f"── {t}"); hdr()
    for h in holds: go(f"  {h}일", cond, hold=h, mk=mk, reg=reg, minn=minn)
    print()

D, R_ = A["drop"], A["rise"]
ORIG = (D < 0.5) & (R_ > 1.5)
REV  = (D > 1.5) & (R_ < 0.5)

print("■ 1) 원안과 반대안 · 보유기간별")
blk("원안: 3개월 급감(<0.5) → 1주 급증(>1.5)", ORIG)
blk("반대: 3개월 급증(>1.5) → 1주 급감(<0.5)", REV)

print("■ 2) 네 사분면 (20일)"); hdr()
go("  급감→급증 (원안)", ORIG, hold=20, minn=30)
go("  급감→급감", (D < 0.5) & (R_ < 0.5), hold=20, minn=30)
go("  급증→급증", (D > 1.5) & (R_ > 1.5), hold=20, minn=30)
go("  급증→급감 (반대)", REV, hold=20, minn=30)
print()

print("■ 3) 문턱 격자 (20일) — drop × rise"); hdr()
for d in (0.3, 0.4, 0.5, 0.7):
    for r in (1.2, 1.5, 2.0, 3.0):
        go(f"  drop<{d} · rise>{r}", (D < d) & (R_ > r), hold=20, minn=30)
print()
print("■ 3b) 반대 방향 격자 (20일)"); hdr()
for d in (1.3, 1.5, 2.0, 3.0):
    for r in (0.3, 0.5, 0.7, 0.8):
        go(f"  drop>{d} · rise<{r}", (D > d) & (R_ < r), hold=20, minn=30)
print()

print("■ 4) 각 축 단독 — 조합이 기여하나 (20일)"); hdr()
for d in (0.3, 0.5, 0.7): go(f"  drop <{d} 단독", D < d, hold=20, minn=30)
for d in (1.3, 1.5, 2.0): go(f"  drop >{d} 단독", D > d, hold=20, minn=30)
for r in (1.2, 1.5, 2.0): go(f"  rise >{r} 단독", R_ > r, hold=20, minn=30)
for r in (0.3, 0.5, 0.7): go(f"  rise <{r} 단독", R_ < r, hold=20, minn=30)
print()

print("■ 5) 창 길이 변형 (20일) — '3개월'·'1주' 정의 바꿔보기"); hdr()
go("  3개월=40일 · 1주=5일", (A.drop40 < 0.5) & (R_ > 1.5), hold=20, minn=30)
go("  3개월=80일 · 1주=5일", (A.drop80 < 0.5) & (R_ > 1.5), hold=20, minn=30)
go("  3개월=60일 · 1주=3일", (D < 0.5) & (A.rise3 > 1.5), hold=20, minn=30)
go("  3개월=60일 · 1주=10일", (D < 0.5) & (A.rise10 > 1.5), hold=20, minn=30)
go("  3개월=60일 · 1개월=20일", (D < 0.5) & (A.risem > 1.5), hold=20, minn=30)
print()

print("■ 6) 신용잔고 절대 수준으로 나누기 (원안 · 20일)"); hdr()
go("  원안 + 1년평균 비율 ≥1%", ORIG & (A.cr250 >= 1), hold=20, minn=30)
go("  원안 + 1년평균 비율 <1%", ORIG & (A.cr250 < 1), hold=20, minn=30)
go("  원안 + 당일 비율 ≥2%", ORIG & (A.rate >= 2), hold=20, minn=30)
go("  원안 + 당일 비율 <0.5%", ORIG & (A.rate < 0.5), hold=20, minn=30)
print()

print("■ 7) 시장·국면 (원안 · 20일)"); hdr()
for mk in ("KOSPI", "KOSDAQ"): go(f"  {mk}", ORIG, hold=20, mk=mk, minn=25)
for rg in ("UP", "SIDE", "DN"): go(f"  {rg}", ORIG, hold=20, reg=rg, minn=25)
print("■ 7b) 시장·국면 (반대안 · 20일)"); hdr()
for mk in ("KOSPI", "KOSDAQ"): go(f"  {mk}", REV, hold=20, mk=mk, minn=25)
for rg in ("UP", "SIDE", "DN"): go(f"  {rg}", REV, hold=20, reg=rg, minn=25)
print()

print("■ 8) 우리 재료 얹기 (원안 · 20일)"); hdr()
go("  + 20일 낙폭 -20% 이하", ORIG & (A.ret20 <= -20), hold=20, minn=30)
go("  + 20일 낙폭 -10% 이하", ORIG & (A.ret20 <= -10), hold=20, minn=30)
go("  + 60일선 위", ORIG & (A.dma60 > 0), hold=20, minn=30)
go("  + 외인 20일 ≥1", ORIG & (A.fw20 >= 1), hold=20, minn=30)
go("  + 공매도 감소(sr20 ≤0)", ORIG & (A.sr20 <= 0), hold=20, minn=30)
go("  + 거래대금 100억↑", ORIG & (A.amt20 >= 100), hold=20, minn=30)
print()
print("■ 8b) 우리 재료 얹기 (반대안 · 20일)"); hdr()
go("  + 20일 낙폭 -20% 이하", REV & (A.ret20 <= -20), hold=20, minn=30)
go("  + 60일선 위", REV & (A.dma60 > 0), hold=20, minn=30)
go("  + 외인 20일 ≥1", REV & (A.fw20 >= 1), hold=20, minn=30)
go("  + 거래대금 100억↑", REV & (A.amt20 >= 100), hold=20, minn=30)
print()

for nm, cond in (("원안", ORIG), ("반대안", REV)):
    Y = go("", cond, hold=20, minn=1, quiet=True)
    if len(Y):
        yr = Y.groupby("yr").agg(n=("r","size"), avg=("r","mean"), med=("r","median"),
                                 win=("r", lambda s: (s>0).mean()*100), al=("alpha","mean"))
        print(f"■ 연도별 ({nm} · 20일)")
        for y, r in yr.iterrows():
            print(f"   {y}  {int(r.n):>4}건  평균 {r.avg:>+6.2f}%  중앙 {r.med:>+5.1f}  승률 {r.win:>3.0f}%  초과 {r.al:>+5.2f}")
        print(f"   최다 연도 {Y.yr.value_counts(normalize=True).max():.0%} · 신호 난 달 {Y.ym.nunique()}개월 · 종목 {Y.ticker.nunique()}개\n")
