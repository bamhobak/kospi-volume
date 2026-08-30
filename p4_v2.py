# -*- coding: utf-8 -*-
"""P4 v2 — SG 가드를 '2년수익≤100%' 에서 '지속상승 AND 대폭상승' 복합조건으로 교체"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/bull_feat.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
g=D.groupby("ticker",sort=False)
D["ret250"]=g.close.transform(lambda x:x/x.shift(250)-1)*100
D["ret500"]=g.close.transform(lambda x:x/x.shift(500)-1)*100
D["above20"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
CASH=3_000_000
BASE=((D.fromhi>=-10)&(D.r16<120)&(D.rw1<=120)&(D.fw5>=3)&(D.fw60>=1)&(D.vol20<=3)
      &(D.sr20<=1)&(D.ret20<=10)&(D.amt20>=50)&(~D.dil)).fillna(False)
OLD=BASE&(D.ret500<=100).fillna(True)
# 배제: 최근 1년 중 70% 넘는 날을 20일선 위에서 보냈고 AND 1년수익 120% 초과
PUMP=((D.above20>70)&(D.ret250>120)).fillna(False)
NEW=BASE&~PUMP
def blk(m,lab):
    x=D[m]
    a=x[x.y<=2022].n40.dropna(); b=x[x.y>=2023].n40.dropna()
    r=b.values; pf=r[r>0].sum()/abs(r[r<=0].sum())
    u=x[(x.y>=2023)&x.k60].n40.dropna(); dn=x[(x.y>=2023)&~x.k60].n40.dropna()
    print(f"| {lab} | {int(m.sum()):,} | {a.mean():+.2f}% | **{b.mean():+.2f}%** | {np.median(b):+.2f}% | "
          f"{(r>0).mean()*100:.0f}% | {pf:.2f} | {x.n40.min():.1f}% | {u.mean():+.2f}% | {dn.mean():+.2f}% | {b.sum()/100*CASH/1e4:+,.0f}만 |")
print("## 가드 비교 (P4 나머지 조건 동일)\n")
print("| 가드 | 신호 | 학습 | **검증** | 검증중앙 | 승률 | PF | 최악 | 검증상승장 | 검증하락장 | 300만원씩 |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
blk(BASE,"없음")
blk(OLD,"현행 2년수익≤100%")
blk(NEW,"**신규 지속상승 배제**")
X=D[NEW].copy(); X["ym"]=X.date.str[:6]; V=X[X.y>=2023]
print(f"\n신규 가드 배제 건수: {int((BASE&PUMP).sum())}건 (SG 45건 포함) · SG 잔존 {int((NEW&D.ticker.isin(['004690','017390','016710','004360','030210','003380','003100','032190'])&(D.y==2023)).sum())}건")
print(f"월평균 {len(X)/104:.1f}건 · 검증 월평균 {len(V)/44:.1f}건 · 신호 있는 달 {V.ym.nunique()}/44")
print("\n## 연도별 (신규 가드)\n\n| 연도 | 건수 | 평균 | 승률 |\n|---|---|---|---|")
for y,gg in X.groupby("y"):
    r=gg.n40.dropna(); print(f"| {y} | {len(r)} | **{r.mean():+.2f}%** | {(r>0).mean()*100:.0f}% |")
print("\n## 배제된 종목들 (신규 가드가 걸러낸 것)\n")
Z=D[BASE&PUMP]
print("| 종목 | 건수 | 평균 40일 수익 |\n|---|---|---|")
for (t,n),gg in Z.groupby(["ticker","name"]):
    print(f"| {n} | {len(gg)} | **{gg.n40.mean():+.1f}%** |")
