# -*- coding: utf-8 -*-
"""시총·회전율·PBR 단일조건 실측 (학습 2018~22, 안정성 기준)"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
def scan(path,label,h,amtmin):
    D=pd.read_pickle(path)
    B=D[((D.close>=1000)&(~D.dil)&(D.amt20>=amtmin)&(D.y<=2022)).fillna(False)]
    base=B[f"n{h}"].dropna()
    print(f"\n## {label} · {h}일 — 기준선 승률 {(base>0).mean()*100:.0f}% 중앙 {np.median(base):+.2f}% 평균 {base.mean():+.2f}%\n")
    C=[]; a=lambda nm,s:C.append((nm,s))
    for q in (300,1000,3000,10000,30000): a(f"시총 ≥ {q:,}억",B.marcap>=q)
    for q in (500,1000,3000,10000): a(f"시총 ≤ {q:,}억",B.marcap<=q)
    for q in (0.3,0.5,1,2,3): a(f"회전율 ≥ {q}%",B.회전율>=q)
    for q in (0.2,0.5,1,2): a(f"회전율 ≤ {q}%",B.회전율<=q)
    for q in (0.5,1,2): a(f"PBR ≤ {q}",B.PBR<=q)
    for q in (1,2,3): a(f"PBR ≥ {q}",B.PBR>=q)
    for q in (1,3,5): a(f"자사주 ≥ {q}%",B.자사주>=q)
    a("자사주 없음",B.자사주.fillna(0)<0.5)
    for q in (90,95): a(f"유통비중 ≥ {q}%",B.유통비중>=q)
    R=[]
    for nm,s in C:
        x=B[s.fillna(False)][f"n{h}"].dropna()
        if len(x)<3000: continue
        R.append((nm,len(x),x.mean(),np.median(x),(x>0).mean()*100,np.percentile(x,5)))
    R.sort(key=lambda r:-r[4])
    print("| 조건 | 표본 | 평균 | 중앙값 | **승률** | 하위5% |\n|---|---|---|---|---|---|")
    for nm,n,m,md,w,p5 in R[:10]: print(f"| {nm} | {n:,} | {m:+.2f}% | {md:+.2f}% | **{w:.0f}%** | {p5:.1f}% |")
    print("하위 4: "+" · ".join(f"{nm}({w:.0f}%)" for nm,_,_,_,w,_ in R[-4:]))
for h in (20,40): scan("data/kp_cap.pkl","코스피",h,10)
for h in (20,40): scan("data/kq_cap.pkl","코스닥",h,5)
