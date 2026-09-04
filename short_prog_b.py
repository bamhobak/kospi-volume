# -*- coding: utf-8 -*-
"""통과 셀 정밀 검증 — 공매도 식음(<0.7) + 차익 순매도(pa20<-0.3).
이웃 문턱·보유기간·시장·국면·연도·중복신호·각 축 단독 기여도.
"""
exec(open("short_prog_test.py",encoding="utf-8").read().split("ok=A.sr.notna()")[0])
COOL=A.sr<0.7
print(f"기간 {A.loc[A.pa20.notna(),'date'].min()}~{A.loc[A.pa20.notna(),'date'].max()}\n")
print("■ 이웃 문턱: 공매도 × 차익순매도 (20일)"); hdr()
for s in (0.5,0.6,0.7,0.8,0.9):
    for p in (-0.2,-0.3,-0.5,-1.0):
        go(f"  공매도<{s} · pa20<{p}", (A.sr<s)&(A.pa20<p), hold=20, minn=30)
print()
print("■ 각 축 단독 — 조합이 진짜 기여하나 (20일)"); hdr()
go("  차익 순매도 pa20<-0.3 단독", A.pa20<-0.3, hold=20, minn=30)
go("  공매도<0.7 단독", COOL, hold=20, minn=30)
go("  공매도≥0.7 · pa20<-0.3 (여집합)", (A.sr>=0.7)&(A.pa20<-0.3), hold=20, minn=30)
go("  공매도<0.7 · pa20≥-0.3 (여집합)", COOL&(A.pa20>=-0.3), hold=20, minn=30)
print()
print("■ 보유기간"); hdr()
for h in (5,10,15,20,30,40,60): go(f"  {h}일", COOL&(A.pa20<-0.3), hold=h, minn=30)
print()
print("■ 시장·국면"); hdr()
for mk in ("KOSPI","KOSDAQ"): go(f"  {mk}", COOL&(A.pa20<-0.3), hold=20, mk=mk, minn=25)
for rg in ("UP","SIDE","DN"): go(f"  {rg}", COOL&(A.pa20<-0.3), hold=20, reg=rg, minn=25)
print()
print("■ 우리 재료 얹기 (20일)"); hdr()
go("  +60일선 위", COOL&(A.pa20<-0.3)&(A.dma60>0), hold=20, minn=30)
go("  +외인 20일 ≥1", COOL&(A.pa20<-0.3)&(A.fw20>=1), hold=20, minn=30)
go("  +비차익 순매수 pn20>0", COOL&(A.pa20<-0.3)&(A.pn20>0), hold=20, minn=30)
go("  +거래대금 100억↑", COOL&(A.pa20<-0.3)&(A.amt20>=100), hold=20, minn=30)
Y=go("", COOL&(A.pa20<-0.3), hold=20, minn=1, quiet=True)
if len(Y):
    yr=Y.groupby("yr").agg(n=("r","size"),avg=("r","mean"),med=("r","median"),win=("r",lambda s:(s>0).mean()*100),al=("alpha","mean"))
    print("\n■ 연도별 (공매도<0.7 · pa20<-0.3 · 20일)")
    for y,r in yr.iterrows(): print(f"   {y}  {int(r.n):>4}건  평균 {r.avg:>+6.2f}%  중앙 {r.med:>+5.1f}  승률 {r.win:>3.0f}%  초과 {r.al:>+5.2f}")
    print(f"   최다 연도 {Y.yr.value_counts(normalize=True).max():.0%} · 신호 난 달 {Y.ym.nunique()}개월 · 종목 {Y.ticker.nunique()}개")
    top=Y.groupby("ticker").size().sort_values(ascending=False).head(3)
    print(f"   최다 종목: " + " · ".join(f"{t} {int(n)}건" for t,n in top.items()))
