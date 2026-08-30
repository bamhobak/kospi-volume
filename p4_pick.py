# -*- coding: utf-8 -*-
"""최종 후보 3종 비교 — 선별근거는 '학습기간 성적 + 구조', 검증은 결과 보고용"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/bull_feat.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
g=D.groupby("ticker",sort=False); D["ret500"]=g.close.transform(lambda x:x/x.shift(500)-1)*100
CASH=3_000_000
def P4(d,**o):
    m=((d.fromhi>=-10)&(d.r16<o.get("r16",120))&(d.rw1<=120)&(d.fw5>=o.get("fw5",3))&(d.fw60>=1)
       &(d.vol20<=3)&(d.sr20<=1)&(d.ret20<=10)&(d.amt20>=o.get("amt",10))&(~d.dil)&(d.ret500<=100))
    if o.get("srd"): m&=(d.srd==True)
    return m.fillna(False)
CAND=[("A 기본",{}),("B 거래대금>=50억",{"amt":50}),("C 외인5일>=10",{"fw5":10})]
KY={2019:7.7,2020:30.8,2021:3.6,2022:-24.9,2023:18.7,2024:-9.6,2025:75.7,2026:57.5}
for lab,o in CAND:
    X=D[P4(D,**o)].copy()
    IS=X[X.y<=2022].n40.dropna(); OS=X[X.y>=2023].n40.dropna()
    r=OS.values; pf=r[r>0].sum()/abs(r[r<=0].sum())
    print(f"\n### {lab} — 전체 {len(X):,}건 · 월 {len(X)/104:.1f}건")
    print(f"- 학습 {len(IS):,}건 **{IS.mean():+.2f}%** 중앙 {np.median(IS):+.2f}% 승률 {(IS>0).mean()*100:.0f}%")
    print(f"- 검증 {len(OS):,}건 **{OS.mean():+.2f}%** 중앙 {np.median(OS):+.2f}% 승률 {(r>0).mean()*100:.0f}% PF {pf:.2f} 최악 {r.min():+.0f}%")
    up=X[(X.y>=2023)&X.k60].n40.dropna(); dn=X[(X.y>=2023)&~X.k60].n40.dropna()
    print(f"- 검증 상승장 {len(up):,}건 **{up.mean():+.2f}%** / 하락장 {len(dn):,}건 **{dn.mean():+.2f}%**")
    ys=[]
    for y,gg in X.groupby("y"):
        rr=gg.n40.dropna(); ys.append(f"{y} {len(rr)}건 {rr.mean():+.1f}%")
    print("- 연도: "+" · ".join(ys))
    # 상위 5건 제외 (소수 대박 의존도)
    o2=np.sort(OS.values)[:-5]
    print(f"- 검증에서 상위 5건 빼면: **{o2.mean():+.2f}%** (의존도 {OS.mean()-o2.mean():+.2f}%p)")
    print(f"- 300만원씩 검증기간 총 {OS.sum()/100*CASH/1e4:+,.0f}만원")
