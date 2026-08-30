# -*- coding: utf-8 -*-
"""업종 폭락이 '시장 폭락'과 별개인가 — 시장은 멀쩡한데 업종만 무너진 경우 (새 규칙 후보)"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
K=pd.read_pickle("data/kp_up.pkl"); Q=pd.read_pickle("data/kq_up.pkl")
def blk(D,label,safe,h):
    B=D[safe]
    print(f"\n## {label} · {h}일 — 시장 국면 × 업종 상태 (학습 2018~22)\n")
    B=B[B.y<=2022]
    print("| 시장 | 업종 60일 | 표본 | 평균 | 중앙값 | 승률 | 하위5% |\n|---|---|---|---|---|---|---|")
    for mlab,mm in [("상승장(60일선 위)",B.k60),("하락장(아래)",~B.k60)]:
        for ulab,uu in [("≤ -20% (업종 폭락)",B.u60<=-20),("-20~-10%",(B.u60>-20)&(B.u60<=-10)),
                        ("-10~0%",(B.u60>-10)&(B.u60<=0)),("0% 초과",B.u60>0)]:
            x=B[(mm&uu).fillna(False)][f"n{h}"].dropna()
            if len(x)<300: continue
            print(f"| {mlab} | {ulab} | {len(x):,} | {x.mean():+.2f}% | {np.median(x):+.2f}% | **{(x>0).mean()*100:.0f}%** | {np.percentile(x,5):.1f}% |")
SK=((K.close>=1000)&(~K.dil)&(K.amt20>=10)).fillna(False)
SQ=((Q.close>=1000)&(~Q.dil)&(Q.amt20>=5)).fillna(False)
blk(K,"코스피",SK,20); blk(Q,"코스닥",SQ,20)
print("\n## 기존 P3·D1 의 업종 임계값을 -20% 로 강화하면?\n")
import csv
# P3
K["srd_"]=K.srd
P3=((K.ret20<=-20)&(K.su1>=2)&(K.fw60>=1)&(K.amt20>=3)&(~K.k60)&(K.srd==True)&(~K.dil)).fillna(False)
print("| 규칙 | 업종 임계 | 건수 | 학습 | **검증** | 중앙값 | 승률 | PF | 최악 |\n|---|---|---|---|---|---|---|---|---|")
for th in (None,-10,-15,-20,-25):
    m=P3 if th is None else (P3&(K.u60.isna()|(K.u60<=th)))
    s=K[m.fillna(False)]
    a=s[s.y<=2022].n20.dropna(); b=s[s.y>=2023].n20.dropna()
    if len(b)<15: continue
    r=b.values; pf=r[r>0].sum()/abs(r[r<=0].sum())
    print(f"| P3 | {th if th else '없음'} | {len(s)} | {a.mean():+.2f}% | **{r.mean():+.2f}%** | {np.median(r):+.2f}% | {(r>0).mean()*100:.0f}% | {pf:.2f} | {r.min():.0f}% |")
D1=((Q.ret20<=-20)&(Q.su1>=2)&(Q.fw60>=1)&(Q.amt20>=2)&(~Q.k60)&(Q.srd==True)&(~Q.dil)
    &(Q.close>=1000)&(Q.ow20>=0)).fillna(False)
for th in (None,-15,-20,-25):
    m=D1 if th is None else (D1&(Q.u60.isna()|(Q.u60<=th)))
    s=Q[m.fillna(False)]
    a=s[s.y<=2022].n20.dropna(); b=s[s.y>=2023].n20.dropna()
    if len(b)<10: continue
    r=b.values; pf=r[r>0].sum()/abs(r[r<=0].sum()) if (r<=0).any() else 99
    print(f"| D1 | {th if th else '없음'} | {len(s)} | {a.mean():+.2f}% | **{r.mean():+.2f}%** | {np.median(r):+.2f}% | {(r>0).mean()*100:.0f}% | {pf:.2f} | {r.min():.0f}% |")
