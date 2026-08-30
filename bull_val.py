# -*- coding: utf-8 -*-
"""검증 — 학습기간에서 고른 상위 40개를 검증기간(2023~26)에서 한 번만 본다.
   추가: 기존 P3 규칙과의 중복도 · 연도별 · 상승장 신호빈도
"""
import io,sys,pickle,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/bull_feat.pkl")
rows=pickle.load(open("data/bull_cand.pkl","rb"))
OS=D[D.y>=2023]; IS=D[D.y<=2022]

def mask(d,p):
    m=(~d.dil)&(d.amt20>=p["amt"])
    for k,f in [("sr",lambda v:d.sr20<=v),("dma",lambda v:d.dma20<=v),("ret20",lambda v:d.ret20<=v),
                ("fh",lambda v:d.fromhi<=v),("fw",lambda v:d.fw60>=v),("fw5",lambda v:d.fw5>=v),
                ("su",lambda v:d.su1>=v),("vol",lambda v:d.vol20<=v),("clv",lambda v:d.clv>=v)]:
        if p.get(k) is not None: m&=f(p[k])
    if p["srd"]: m&=(d.srd==True)
    return m.fillna(False)
# 기존 P3 (사이트 규칙)
def p3(d):
    return ((d.ret20<=-20)&(d.su1>=2)&(d.fw60>=1)&(d.amt20>=3)&(~d.k60)&(d.srd==True)&(~d.dil)).fillna(False)

print("## 검증기간(2023~26) 성적 — 학습에서 고른 40개 전부 공개\n")
print("| # | 보유 | 학습 상승 | 학습 하락 | **검증 상승** | (건수) | **검증 하락** | (건수) | 검증 전체 | P3중복 |")
print("|---|---|---|---|---|---|---|---|---|---|")
P3o=OS[p3(OS)]; P3set=set(zip(P3o.date,P3o.ticker))
keep=[]
for i,(p,h,n,mn,nu,mu,nd,md,w) in enumerate(rows,1):
    m=mask(OS,p).values; U=OS.k60.values
    col=OS[f"n{h}"].values
    u=col[m&U]; dd=col[m&~U]
    u=u[np.isfinite(u)]; dd=dd[np.isfinite(dd)]
    a=col[m]; a=a[np.isfinite(a)]
    x=OS[m]; ov=len(P3set & set(zip(x.date,x.ticker)))/max(len(x),1)*100
    keep.append((i,p,h,mu,md,u,dd,a,ov))
    if i<=15:
        print(f"| {i} | {h}일 | {mu:+.1f}% | {md:+.1f}% | **{u.mean() if len(u) else float('nan'):+.2f}%** | {len(u)} | "
              f"**{dd.mean() if len(dd) else float('nan'):+.2f}%** | {len(dd)} | {a.mean():+.2f}% | {ov:.0f}% |")
uu=[k[5].mean() for k in keep if len(k[5])>=15]
dd2=[k[6].mean() for k in keep if len(k[6])>=15]
print(f"\n**40개 전체 검증 분포** — 상승장 수익 중앙값 {np.median(uu):+.2f}% (양수 {sum(1 for v in uu if v>0)}/{len(uu)}) · "
      f"하락장 중앙값 {np.median(dd2):+.2f}% (양수 {sum(1 for v in dd2 if v>0)}/{len(dd2)})")
print(f"기존 P3와의 신호 중복률 중앙값 {np.median([k[8] for k in keep]):.0f}%")

print("\n## 무작위 기준선 대비 — 같은 국면에서 아무 종목이나 (검증기간)\n")
for lab,mm in [("상승장",OS.k60),("하락장",~OS.k60)]:
    for h in (20,40):
        v=OS[mm][f"n{h}"].dropna()
        print(f"- {lab} {h}일: {v.mean():+.2f}% (표본 {len(v):,})")
