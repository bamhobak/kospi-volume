# -*- coding: utf-8 -*-
"""배분안 정면 비교 — 60시드, 총 노출 100 이내로 설계된 조합들"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
from sizing_core import *
def ev2(size,cap,seeds=60):
    o=[]
    for s in range(seeds):
        e1,m1,_=sim(size,cap,*IS,s); e2,m2,n2=sim(size,cap,*OS,s)
        o.append((((e1/100)**(1/YIS)-1)*100,m1,((e2/100)**(1/YOS)-1)*100,m2,n2))
    o=np.array(o); return o
SCHEMES=[
 ("A 균등 8% · 각 6종목",       {"P2":8,"P3":8,"P4":8,"D1":8},  {"P2":3,"P3":3,"P4":6,"D1":3}),
 ("B 보수 5% · 폭락규칙 넉넉",   {"P2":5,"P3":5,"P4":5,"D1":5},  {"P2":4,"P3":6,"P4":8,"D1":6}),
 ("C 권장안",                   {"P2":15,"P3":5,"P4":10,"D1":5},{"P2":2,"P3":4,"P4":6,"D1":4}),
 ("D P4 집중",                  {"P2":15,"P3":5,"P4":12,"D1":5},{"P2":2,"P3":3,"P4":7,"D1":3}),
 ("E 폭락규칙 배제(P4+P2만)",    {"P2":15,"P3":0,"P4":12,"D1":0},{"P2":2,"P3":0,"P4":7,"D1":0}),
 ("F 공격 20%",                 {"P2":20,"P3":10,"P4":15,"D1":10},{"P2":2,"P3":3,"P4":5,"D1":3}),
]
sz=lambda d:[d[k] for k in ORDER]
print("## 배분안 비교 — 60시드 평균 (계좌 100, 레버리지 없음)\n")
print("| 배분안 | 최대노출 | 학습 연평균 | 학습 MDD | **검증 연평균** | 검증 MDD | 검증 표준편차 | 검증 손실확률 |")
print("|---|---|---|---|---|---|---|---|")
res={}
for nm,size,cap in SCHEMES:
    o=ev2(sz(size),sz(cap)); res[nm]=o
    expo=sum(size[k]*cap[k] for k in ORDER)
    print(f"| {nm} | {expo}% | {o[:,0].mean():+.1f}% | {o[:,1].mean():.0f}% | **{o[:,2].mean():+.1f}%** | "
          f"{o[:,3].mean():.0f}% | {o[:,2].std():.1f}%p | {(o[:,2]<0).mean()*100:.0f}% |")
print("\n## 위험조정 (연평균 ÷ MDD) — 두 기간 모두\n")
print("| 배분안 | 학습 | 검증 | 낮은 쪽 |\n|---|---|---|---|")
for nm in res:
    o=res[nm]; a=o[:,0].mean()/max(o[:,1].mean(),1); b=o[:,2].mean()/max(o[:,3].mean(),1)
    print(f"| {nm} | {a:.2f} | {b:.2f} | **{min(a,b):.2f}** |")
print("\n## 권장안(C)의 실제 자금 사용률\n")
size={"P2":15,"P3":5,"P4":10,"D1":5}; cap={"P2":2,"P3":4,"P4":6,"D1":4}
for k in ORDER:
    print(f"- {k}: 종목당 {size[k]} × 최대 {cap[k]}종목 = 최대 {size[k]*cap[k]}")
print(f"- 이론상 최대 합계 {sum(size[k]*cap[k] for k in ORDER)} (동시에 다 차는 일은 실측상 없음)")
