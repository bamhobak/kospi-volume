# -*- coding: utf-8 -*-
"""재무 지표 실측 1 — 단일조건 (학습 2018~22 만, 안정성 기준)"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
def load(feat,fin):
    D=pd.read_pickle(feat); F=pd.read_pickle(fin)
    F=F.rename(columns={"sc":"ticker"}).drop(columns=["d"],errors="ignore")
    return D.merge(F,on=["date","ticker"],how="left")
K=load("data/bull_feat.pkl","data/kp_fin.pkl"); Q=load("data/kd_feat.pkl","data/kq_fin.pkl")
def scan(D,label,h,safe):
    B=D[safe&(D.y<=2022)]
    base=B[f"n{h}"].dropna()
    print(f"\n## {label} · {h}일 — 기준선 승률 {(base>0).mean()*100:.0f}% 중앙 {np.median(base):+.2f}% 평균 {base.mean():+.2f}%\n")
    C=[]; a=lambda nm,s:C.append((nm,s))
    for q in (0,5,10,15): a(f"ROE ≥ {q}%",B.ROE>=q)
    for q in (0,-10): a(f"ROE ≤ {q}%",B.ROE<=q)
    for q in (50,100,200): a(f"부채비율 ≤ {q}%",B.부채비율<=q)
    for q in (200,300): a(f"부채비율 ≥ {q}%",B.부채비율>=q)
    a("자본잠식",B.자본잠식==1); a("자본잠식 아님",B.자본잠식==0)
    for q in (30,50,70): a(f"자기자본비율 ≥ {q}%",B.자본자산>=q)
    for q in (0,5,10): a(f"영업이익률 ≥ {q}%",B.영업이익률>=q)
    for q in (0,-10): a(f"영업이익률 ≤ {q}%",B.영업이익률<=q)
    for q in (0,10,30): a(f"매출성장 ≥ {q}%",B.매출성장>=q)
    for q in (0,-10): a(f"매출성장 ≤ {q}%",B.매출성장<=q)
    for q in (0,20): a(f"영업이익성장 ≥ {q}%",B.영업이익성장>=q)
    a("흑자전환",B.흑자전환==1); a("3년 연속흑자",B.연속흑자>=3)
    a("재무 데이터 없음",B.ROE.isna())
    R=[]
    for nm,s in C:
        x=B[s.fillna(False)][f"n{h}"].dropna()
        if len(x)<3000: continue
        R.append((nm,len(x),x.mean(),np.median(x),(x>0).mean()*100,np.percentile(x,5)))
    R.sort(key=lambda r:-r[4])
    print("| 재무 조건 | 표본 | 평균 | 중앙값 | **승률** | 하위5% |\n|---|---|---|---|---|---|")
    for nm,n,m,md,w,p5 in R[:9]: print(f"| {nm} | {n:,} | {m:+.2f}% | {md:+.2f}% | **{w:.0f}%** | {p5:.1f}% |")
    print("하위 4: "+" · ".join(f"{nm}({w:.0f}%)" for nm,_,_,_,w,_ in R[-4:]))
SK=((K.close>=1000)&(~K.dil)&(K.amt20>=10)).fillna(False)
SQ=((Q.close>=1000)&(~Q.dil)&(Q.amt20>=5)).fillna(False)
for h in (20,40): scan(K,"코스피",h,SK)
for h in (20,40): scan(Q,"코스닥",h,SQ)
K.to_pickle("data/kp_all.pkl"); Q.to_pickle("data/kq_all.pkl")
