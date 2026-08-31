# -*- coding: utf-8 -*-
"""P4 감사 — 신호가 정말 독립적인가, 폐지종목은 들어있나, 비용·선행편향은 없나"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
K=pd.read_pickle("data/kp_hz2.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
g=K.groupby("ticker",sort=False)
K["lo5"]=g.low.shift(-1).rolling(5,min_periods=1).min().shift(-4)
M=((K.u<=-20)&(K.dma20<=-10)&(K.srd==True)&K.ok).fillna(False)
X=K[M].copy()
hit=((X.lo5/X.buy-1)*100<=-15).values
X["r"]=np.where(hit,-15-X.cost.values,X.n5.values)
X=X.dropna(subset=["r"])
print("## 1) 표본 구성 — 4,339건이 정말 4,339개의 독립 거래인가\n")
print(f"- 신호 {len(X):,}건 · **고유 종목 {X.ticker.nunique()}개** · 고유 날짜 {X.date.nunique()}일")
print(f"- 종목당 평균 {len(X)/X.ticker.nunique():.1f}회 · 날짜당 평균 {len(X)/X.date.nunique():.1f}종목")
# 같은 종목이 며칠 간격으로 반복되나
X=X.sort_values(["ticker","date"])
dates=sorted(K.date.unique()); DI={d:i for i,d in enumerate(dates)}
X["di"]=X.date.map(DI)
X["gap"]=X.groupby("ticker").di.diff()
print(f"- 같은 종목 재신호 간격: 중앙 {X.gap.median():.0f}거래일 · **1일 간격 {int((X.gap==1).sum()):,}건 ({(X.gap==1).mean()*100:.0f}%)**")
print(f"- 보유 5일과 겹치는 재신호(간격≤5): **{int((X.gap<=5).sum()):,}건 ({(X.gap<=5).mean()*100:.0f}%)**")
print("\n→ 같은 종목·같은 하락 국면을 며칠에 걸쳐 중복 계산하고 있다. 독립 표본이 아니다.\n")
print("## 2) 중복 제거 후 — 종목별로 10거래일 안에 한 번만 인정\n")
keep=[]
last={}
for r in X.sort_values("di").itertuples():
    if r.ticker in last and r.di-last[r.ticker]<10: continue
    last[r.ticker]=r.di; keep.append(r.Index)
Y=X.loc[keep]
print(f"- {len(X):,}건 → **{len(Y):,}건** ({len(Y)/len(X)*100:.0f}%)")
def S(d,col="r"):
    r=d[col].values; pf=r[r>0].sum()/abs(r[r<=0].sum()) if (r<=0).any() else 99
    return len(r),r.mean(),np.median(r),(r>0).mean()*100,pf
print("\n| 구간 | 원본 건수 | 원본 평균 | 원본 승률 | 중복제거 건수 | **중복제거 평균** | **승률** | PF |")
print("|---|---|---|---|---|---|---|---|")
for t,a,b in [("전체",X,Y),("학습",X[X.y<=2022],Y[Y.y<=2022]),("검증",X[X.y>=2023],Y[Y.y>=2023])]:
    n1,m1,_,w1,_=S(a); n2,m2,md2,w2,pf2=S(b)
    print(f"| {t} | {n1:,} | {m1:+.2f}% | {w1:.0f}% | {n2:,} | **{m2:+.2f}%** | **{w2:.0f}%** | {pf2:.2f} |")
print("\n## 3) 연도별 — 중복 제거 후\n")
print("| 연도 | 원본 건수 | 원본 평균 | 중복제거 건수 | **중복제거 평균** | 승률 |")
print("|---|---|---|---|---|---|")
for y in range(2018,2027):
    a=X[X.y==y]; b=Y[Y.y==y]
    if not len(b): continue
    print(f"| {y} | {len(a):,} | {a.r.mean():+.1f}% | {len(b):,} | **{b.r.mean():+.2f}%** | {(b.r>0).mean()*100:.0f}% |")
print("\n## 4) 폐지 종목 포함 여부\n")
print(f"- kp_hz2 전체: 생존 {int((K.grp=='생존').sum()):,}행 · **폐지 {int((K.grp=='폐지').sum()):,}행** ({K[K.grp=='폐지'].ticker.nunique()}종목)")
print(f"- P4 신호 중 폐지종목: **{int((X.grp=='폐지').sum())}건**")
pd_=K[(K.grp=='폐지')]
print(f"- 폐지종목이 조건에 근접한 적: 업종-20 통과 {int(((pd_.u<=-20)&pd_.ok).fillna(False).sum()):,}행 · +20일선이격-10 {int(((pd_.u<=-20)&(pd_.dma20<=-10)&pd_.ok).fillna(False).sum()):,}행")
print(f"- 그중 공매도감소까지: {int(((pd_.u<=-20)&(pd_.dma20<=-10)&(pd_.srd==True)&pd_.ok).fillna(False).sum()):,}행")
print(f"- 폐지종목 공매도 데이터 보유율: {pd_.srd.notna().mean()*100:.0f}%")
print("\n## 5) 비용·매수시점 확인\n")
print(f"- 비용 중앙 {X.cost.median():.2f}% (거래대금 구간별 0.38~1.18%)")
print(f"- 매수 = 신호 다음날 시가 (buy 컬럼), 매도 = 5거래일 뒤 종가")
print(f"- 손절 -15% 발동 {hit.mean()*100:.0f}% · 손절 없을 때 최악 {X.n5.min():.1f}% → 손절 후 {X.r.min():.1f}%")
