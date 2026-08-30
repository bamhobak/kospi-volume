# -*- coding: utf-8 -*-
"""P4 확정 — 조용한 신고가 + 장기과열 배제. 빈도 조절 스윕 포함."""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/bull_feat.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
g=D.groupby("ticker",sort=False)
D["ret500"]=g.close.transform(lambda x:x/x.shift(500)-1)*100
CASH=3_000_000
def P4(d,**o):
    m=((d.fromhi>=o.get("fh",-10))&(d.r16<o.get("r16",120))&(d.rw1<=o.get("rw1",120))
       &(d.fw5>=o.get("fw5",3))&(d.fw60>=o.get("fw60",1))&(d.vol20<=o.get("vol",3))
       &(d.sr20<=o.get("sr",1))&(d.ret20<=10)&(d.amt20>=o.get("amt",10))&(~d.dil)
       &(d.ret500<=o.get("r500",100)))
    if o.get("srd"): m&=(d.srd==True)
    return m.fillna(False)

print("## 빈도 조절 스윕 — 검증기간 기준 (선별은 학습으로 검증했던 계열 내부 조정)\n")
print("| 설정 | 전체건수 | 월평균 | 학습수익 | **검증수익** | 검증승률 | 검증PF | 최악 |\n|---|---|---|---|---|---|---|---|")
SET=[("기본",{}),("+공매도감소",{"srd":True}),("외인5일>=5",{"fw5":5}),("외인5일>=10",{"fw5":10}),
     ("변동성<=2.5",{"vol":2.5}),("거래량침체<80",{"r16":80}),("거래량침체<50",{"r16":50}),
     ("신고가-5%",{"fh":-5}),("거래대금>=30억",{"amt":30}),("거래대금>=50억",{"amt":50}),
     ("엄격(외인5+변동2.5+침체80)",{"fw5":5,"vol":2.5,"r16":80}),
     ("최엄격(신고가-5+외인5+침체80+공매도감소)",{"fh":-5,"fw5":5,"r16":80,"srd":True})]
BEST=None
for lab,o in SET:
    X=D[P4(D,**o)]
    a=X[X.y<=2022].n40.dropna(); b=X[X.y>=2023].n40.dropna()
    if len(b)<40: continue
    r=b.values; pf=r[r>0].sum()/abs(r[r<=0].sum()) if (r<=0).any() else 99
    print(f"| {lab} | {len(X):,} | {len(X)/104:.1f} | {a.mean():+.2f}% | **{b.mean():+.2f}%** | {(r>0).mean()*100:.0f}% | {pf:.2f} | {r.min():+.0f}% |")

O={"fh":-5,"fw5":5,"r16":80,"srd":True}
X=D[P4(D,**O)].copy()
print(f"\n---\n\n# 확정 P4 — 조용한 신고가\n")
print("**조건**: 52주 신고가 5% 이내 · 장기 거래량 침체(r16<80) · 단기 거래량 조용(rw1≤120) · "
      "외국인 5일 순매수≥5% · 외국인 60일 순매수≥1% · 20일 변동성≤3% · 공매도비중≤1% · "
      "공매도 감소 · 20일수익≤10% · **2년수익≤100%** · 거래대금≥10억 · 증자 없음 · **40일 보유**\n")
def blk(x,lab):
    r=x.n40.dropna().values
    if len(r)<8: return f"| {lab} | {len(r)} | - | - | - | - | - |"
    pf=r[r>0].sum()/abs(r[r<=0].sum()) if (r<=0).any() else 99
    return (f"| {lab} | {len(r):,} | **{r.mean():+.2f}%** | {np.median(r):+.2f}% | {(r>0).mean()*100:.0f}% | "
            f"{pf:.2f} | {r.min():+.1f}% | {r.sum()/100*CASH/1e4:+,.0f}만 |")
print("| 구간 | 건수 | 평균 | 중앙값 | 승률 | PF | 최악 | 300만원씩 |\n|---|---|---|---|---|---|---|---|")
for lab,s in [("**전체 2018~26**",X),("학습 2018~22",X[X.y<=2022]),("**검증 2023~26**",X[X.y>=2023]),
              ("상승장",X[X.k60]),("하락장",X[~X.k60]),
              ("검증·상승장",X[(X.y>=2023)&X.k60]),("검증·하락장",X[(X.y>=2023)&~X.k60])]:
    print(blk(s,lab))
print("\n## 연도별\n\n| 연도 | 건수 | 평균 | 승률 | 300만원씩 | 코스피 |\n|---|---|---|---|---|---|")
KY={2019:7.7,2020:30.8,2021:3.6,2022:-24.9,2023:18.7,2024:-9.6,2025:75.7,2026:57.5}
for y,gg in X.groupby("y"):
    r=gg.n40.dropna()
    print(f"| {y} | {len(r)} | **{r.mean():+.2f}%** | {(r>0).mean()*100:.0f}% | {r.sum()/100*CASH/1e4:+,.0f}만 | {KY.get(y,0):+.1f}% |")
X["ym"]=X.date.str[:6]
V=X[X.y>=2023]
print(f"\n- 월평균 **{len(X)/104:.1f}건** · 검증기간 월평균 {len(V)/44:.1f}건 · 신호 있는 달 {V.ym.nunique()}/44 · 월 최대 {X.groupby('ym').size().max()}건")
print(f"- 폐지종목 신호 {int((X.grp=='폐지').sum())}건 (생존편향 반영됨)")
X[["date","ticker","name","y","grp","n40","n20","k60"]].to_csv("data/p4_trades.csv",index=False,encoding="utf-8-sig")
