# -*- coding: utf-8 -*-
"""3단계: 신고가 근접 베이스 위 한계효과 (학습 2018~22 만)"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/bull_feat.pkl"); IS=D[D.y<=2022]

print("## 신고가 근접 임계값 스윕 (상승장·학습기간)\n")
print("| 국면 | fromhi | 보유 | 표본 | 알파 | 절대수익 | 알파승률 |\n|---|---|---|---|---|---|---|")
for reg,rm in [("60일선 위",IS.k60),("60·20일선 위",IS.k60&IS.k20),("무조건",pd.Series(True,index=IS.index))]:
    for th in (-10,-5,-3,-1,0):
        for h in (10,20,40):
            x=IS[rm & (IS.fromhi>=th)][[f"a{h}",f"n{h}"]].dropna()
            if len(x)<200: continue
            print(f"| {reg} | >={th}% | {h}일 | {len(x):,} | **{x[f'a{h}'].mean():+.2f}%** | {x[f'n{h}'].mean():+.2f}% | {(x[f'a{h}']>0).mean()*100:.0f}% |")

B=IS[IS.k60 & (IS.fromhi>=-5)].copy()
for h in (10,20,40):
    base=B[f"a{h}"].mean()
    print(f"\n## 베이스[상승장+신고가근접] 위 한계효과 · {h}일 보유 (기준 알파 {base:+.2f}%)\n")
    C=[]
    def a(nm,s): C.append((nm,s))
    for q in (30,50,80,120): a(f"거래량침체 r16<{q}",B.r16<q)
    for q in (80,120,200): a(f"거래량 rw1>={q}",B.rw1>=q)
    for q in (80,120): a(f"거래량 rw1<={q}",B.rw1<=q)
    for q in (1,2,3): a(f"su1<={q}",B.su1<=q)
    for q in (1,3,5,10): a(f"외국인5일 fw5>={q}",B.fw5>=q)
    for q in (0.5,1,2,3): a(f"외국인60일 fw60>={q}",B.fw60>=q)
    for q in (0,1,2): a(f"기관5일 ow5>={q}",B.ow5>=q)
    for q in (0,1,2): a(f"기관20일 ow20>={q}",B.ow20>=q)
    for q in (0,5,10,20,40): a(f"20일수익 ret20>={q}",B.ret20>=q)
    for q in (5,10,20): a(f"20일수익 ret20<={q}",B.ret20<=q)
    for q in (0,10,20,50): a(f"60일수익 ret60>={q}",B.ret60>=q)
    for q in (20,50,100): a(f"60일수익 ret60<={q}",B.ret60<=q)
    for q in (0,20,50,100): a(f"120일수익 ret120>={q}",B.ret120>=q)
    for q in (0,3,5): a(f"3일수익 ret3<={q}",B.ret3<=q)
    for q in (0,-3): a(f"3일수익 ret3>={q}",B.ret3>=q)
    for q in (3,5,10,20,50,100,300): a(f"거래대금>={q}억",B.amt20>=q)
    for q in (10,30,100): a(f"거래대금<={q}억",B.amt20<=q)
    for q in (2,3,4,5): a(f"변동성<={q}",B.vol20<=q)
    for q in (20,50,100,200): a(f"저점대비 fromlo<={q}",B.fromlo<=q)
    for q in (20,50): a(f"저점대비 fromlo>={q}",B.fromlo>=q)
    a("공매도감소",B.srd==True); a("공매도증가",B.srd==False); a("공매도데이터없음",B.srd.isna())
    for q in (1,3,5): a(f"공매도비중 sr20<={q}",B.sr20<=q)
    a("증자없음",~B.dil)
    a("clv>=0.7",B.clv>=0.7); a("clv<=0.5",B.clv<=0.5)
    for q in (-3,0,1,3): a(f"익일갭<={q}",B.gap<=q)
    a("지수20일선 위",B.k20); a("지수120일선 위",B.k120)
    for q in (0,3,5,10): a(f"20일선이격>={q}",B.dma20>=q)
    for q in (5,10,15): a(f"20일선이격<={q}",B.dma20<=q)
    for q in (0,5,10): a(f"60일선이격>={q}",B.dma60>=q)
    R=[]
    for nm,s in C:
        s=s.fillna(False)
        x=B[s][[f"a{h}",f"n{h}"]].dropna()
        if len(x)<250: continue
        R.append((nm,len(x),x[f"a{h}"].mean(),x[f"a{h}"].mean()-base,(x[f"a{h}"]>0).mean()*100,x[f"n{h}"].mean()))
    R.sort(key=lambda r:-r[3])
    print("| 조건 | 표본 | 알파 | **한계효과** | 승률 | 절대 |\n|---|---|---|---|---|---|")
    for nm,n,al,d,w,ab in R[:12]:
        print(f"| {nm} | {n:,} | {al:+.2f}% | **{d:+.2f}%p** | {w:.0f}% | {ab:+.2f}% |")
