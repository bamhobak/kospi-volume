# -*- coding: utf-8 -*-
"""P4 꼬리위험 — 작전주(장기 저변동 급등) 배제 조건 탐색"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/bull_feat.pkl")
D=D.sort_values(["ticker","date"]).reset_index(drop=True)
g=D.groupby("ticker",sort=False)
D["ret250"]=g.close.transform(lambda x:x/x.shift(250)-1)*100
D["ret500"]=g.close.transform(lambda x:x/x.shift(500)-1)*100
def P4(d): return ((d.fromhi>=-10)&(d.r16<120)&(d.rw1<=120)&(d.fw5>=3)&(d.fw60>=1)
            &(d.vol20<=3)&(d.sr20<=1)&(d.ret20<=10)&(d.amt20>=10)&(~d.dil)).fillna(False)
X=D[P4(D)].copy()
SG={"016710","004690","001470","007700","006360","012320","011090","003480"}
sg=X[X.ticker.isin(SG)&(X.y==2023)]
print(f"## SG사태 종목이 P4에 미친 영향\n")
print(f"- 해당 신호 {len(sg)}건 · 평균 {sg.n40.mean():+.1f}% · 손실 합 {sg.n40.sum()/100*300:+,.0f}만원")
y23=X[X.y==2023]
print(f"- 2023년 전체: {len(y23)}건 {y23.n40.mean():+.2f}%  →  SG 제외 시 **{y23[~y23.ticker.isin(SG)].n40.mean():+.2f}%**")
print(f"- 전체기간: {X.n40.mean():+.2f}%  →  SG 제외 시 **{X[~(X.ticker.isin(SG)&(X.y==2023))].n40.mean():+.2f}%**")

print(f"\n## 장기 상승폭 상한 조건 검토 (학습기간에서만 판단)\n")
IS=X[X.y<=2022]
print("| 조건 | 학습 건수 | 학습 수익 | 학습 최악 | 검증 건수 | 검증 수익 | 검증 최악 | SG신호 남음 |\n|---|---|---|---|---|---|---|---|")
CAND=[("무조건",pd.Series(True,index=X.index))]
for q in (50,100,150,200,300):
    CAND.append((f"1년수익<={q}%",X.ret250<=q))
for q in (100,200,300,500):
    CAND.append((f"2년수익<={q}%",X.ret500<=q))
for q in (30,50,80,100):
    CAND.append((f"저점대비<=+{q}%",X.fromlo<=q))
for nm,s in CAND:
    s=s.fillna(False)
    a=X[s&(X.y<=2022)].n40.dropna(); b=X[s&(X.y>=2023)].n40.dropna()
    ns=int((s&X.ticker.isin(SG)&(X.y==2023)).sum())
    if len(a)<50 or len(b)<50: continue
    print(f"| {nm} | {len(a):,} | {a.mean():+.2f}% | {a.min():+.0f}% | {len(b):,} | **{b.mean():+.2f}%** | {b.min():+.0f}% | {ns}건 |")
