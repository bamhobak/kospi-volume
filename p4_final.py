# -*- coding: utf-8 -*-
"""P4 후보 확정 검증 — 조용한 신고가(Quiet Breakout)
   국면 게이트 없음: 상승장에서 벌고 하락장에서 버티는 것이 목표.
"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/bull_feat.pkl"); CASH=3_000_000

def P4(d):
    return ((d.fromhi>=-10)&(d.r16<120)&(d.rw1<=120)&(d.fw5>=3)&(d.fw60>=1)
            &(d.vol20<=3)&(d.sr20<=1)&(d.ret20<=10)&(d.amt20>=10)&(~d.dil)).fillna(False)
# 비교용 기존 규칙
def P1(d): return ((d.r16<50)&(d.rw1>=200)&(d.fw5>=3)&(d.amt>=50)&d.ret10.between(0,20)&d.k5&d.k20&(d.srd==True)&(d.gap<5)).fillna(False)
def P2(d): return ((d.r16<30)&(d.rw1>=200)&(d.fw5>=2)&(d.amt>=3)&(d.ret3<=-5)&(d.ret10<=0)&(~d.k20)&(d.srd==True)&(~d.dil)).fillna(False)
def P3(d): return ((d.ret20<=-20)&(d.su1>=2)&(d.fw60>=1)&(d.amt20>=3)&(~d.k60)&(d.srd==True)&(~d.dil)).fillna(False)

m=P4(D); X=D[m].copy()
print(f"## P4 후보 — 신호 {len(X):,}건 (2018~2026) · 폐지종목 {int((X.grp=='폐지').sum())}건\n")
def blk(x,h,lab):
    r=x[f"n{h}"].dropna().values
    if len(r)<10: return f"| {lab} | {len(r)} | - | - | - | - |"
    pf=r[r>0].sum()/abs(r[r<=0].sum()) if (r<=0).any() else 99
    return (f"| {lab} | {len(r):,} | **{r.mean():+.2f}%** | {np.median(r):+.2f}% | {(r>0).mean()*100:.0f}% | "
            f"{pf:.2f} | {r.min():+.1f}% | {r.sum()/100*CASH/1e4:+,.0f}만 |")
print("| 구간 | 건수 | 평균 | 중앙값 | 승률 | PF | 최악 | 300만원씩 |\n|---|---|---|---|---|---|---|---|")
for lab,sub in [("**전체기간**",X),("학습 2018~22",X[X.y<=2022]),("**검증 2023~26**",X[X.y>=2023]),
                ("상승장(60일선위)",X[X.k60]),("하락장(아래)",X[~X.k60]),
                ("검증·상승장",X[(X.y>=2023)&X.k60]),("검증·하락장",X[(X.y>=2023)&~X.k60])]:
    print(blk(sub,40,lab))

print("\n## 연도별 (40일 보유)\n")
print("| 연도 | 건수 | 평균 | 승률 | 300만원씩 | 코스피 |\n|---|---|---|---|---|---|")
KY={2018:-17.3,2019:7.7,2020:30.8,2021:3.6,2022:-24.9,2023:18.7,2024:-9.6,2025:75.7,2026:57.5}
for y,g in X.groupby("y"):
    r=g.n40.dropna()
    print(f"| {y} | {len(r)} | **{r.mean():+.2f}%** | {(r>0).mean()*100:.0f}% | {r.sum()/100*CASH/1e4:+,.0f}만 | {KY.get(y,0):+.1f}% |")

print("\n## 보유기간·손절 스윕 (검증기간)\n")
V=X[X.y>=2023]
print("| 보유 | 평균 | 승률 | PF |\n|---|---|---|---|")
for h in (10,20,40):
    r=V[f"n{h}"].dropna().values
    pf=r[r>0].sum()/abs(r[r<=0].sum()) if (r<=0).any() else 99
    print(f"| {h}일 | **{r.mean():+.2f}%** | {(r>0).mean()*100:.0f}% | {pf:.2f} |")

print("\n## 기존 규칙과의 중복\n")
s4=set(zip(X.date,X.ticker))
print("| 규칙 | 신호수 | P4와 겹침 |\n|---|---|---|")
for nm,f in [("P1",P1),("P2",P2),("P3",P3)]:
    o=D[f(D)]; s=set(zip(o.date,o.ticker))
    print(f"| {nm} | {len(s):,} | **{len(s&s4)}건** ({len(s&s4)/max(len(s),1)*100:.1f}%) |")

print("\n## 신호 빈도\n")
X["ym"]=X.date.str[:6]
mc=X.groupby("ym").size()
print(f"- 전체 {len(X):,}건 / {X.ym.nunique()}개월 → 월평균 **{len(X)/104:.1f}건**")
V2=X[X.y>=2023]
print(f"- 검증기간 {len(V2):,}건 / 44개월 → 월평균 **{len(V2)/44:.1f}건** · 신호 있는 달 {V2.ym.nunique()}/44")
print(f"- 월 최대 {mc.max()}건 ({mc.idxmax()})")
X[["date","ticker","name","y","grp","n40","n20","k60"]].to_csv("data/p4_trades.csv",index=False,encoding="utf-8-sig")
