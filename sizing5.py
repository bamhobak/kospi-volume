# -*- coding: utf-8 -*-
"""권장안 확정 — 실제 자금 사용률 측정 + 한도 축소판 비교"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
from sizing_core import *
def sim2(size,cap,d0,d1,seed):
    """투자중 비중의 분포까지 기록"""
    rng=np.random.default_rng(seed)
    cash=100.0;peak=100.0;mdd=0.0
    amt=[];ret=[];out=[];rid=[];tks=[];use=[];cnt=[]
    i0=next(i for i,d in enumerate(dates) if d>=d0); i1=max(i for i,d in enumerate(dates) if d<=d1)
    for i in range(i0,i1+1):
        keep=[]
        for j in range(len(amt)):
            if out[j]<=i: cash+=amt[j]*(1+ret[j]/100)
            else: keep.append(j)
        amt=[amt[j] for j in keep];ret=[ret[j] for j in keep]
        out=[out[j] for j in keep];rid=[rid[j] for j in keep];tks=[tks[j] for j in keep]
        eq=cash+sum(amt)
        s=sig[i]
        if s is not None and len(s):
            for j in rng.permutation(len(s)):
                k=int(s[j,0]);tk=TKS[i][j]
                if size[k]<=0: continue
                if sum(1 for x in rid if x==k)>=cap[k]: continue
                if tk in tks: continue
                a=eq*size[k]/100
                if a>cash: continue
                amt.append(a);ret.append(s[j,1]);out.append(i+HOLD[ORDER[k]]);rid.append(k);tks.append(tk);cash-=a
        eq=cash+sum(amt);peak=max(peak,eq);mdd=max(mdd,(peak-eq)/peak*100)
        use.append(sum(amt)/eq*100);cnt.append(len(amt))
    eq=cash+sum(amt[j]*(1+ret[j]/100) for j in range(len(amt)))
    return eq,mdd,np.array(use),np.array(cnt)
sz=lambda d:[d[k] for k in ORDER]
CAND=[
 ("D 원안",       {"P2":15,"P3":5,"P4":12,"D1":5},{"P2":2,"P3":3,"P4":7,"D1":3}),
 ("D-1 한도축소", {"P2":15,"P3":5,"P4":12,"D1":5},{"P2":1,"P3":2,"P4":5,"D1":2}),
 ("D-2 P4 6종목", {"P2":15,"P3":5,"P4":12,"D1":5},{"P2":2,"P3":2,"P4":6,"D1":2}),
 ("D-3 P4 10%",   {"P2":15,"P3":5,"P4":10,"D1":5},{"P2":2,"P3":3,"P4":7,"D1":3}),
 ("D-4 P3D1 8%",  {"P2":15,"P3":8,"P4":12,"D1":8},{"P2":2,"P3":3,"P4":7,"D1":3}),
]
print("## 후보 비교 — 60시드\n")
print("| 안 | 이론최대 | 학습 연평균 | 학습MDD | **검증 연평균** | 검증MDD | 실제 투자율 중앙 | 투자율 90%분위 | 평균 보유종목 |")
print("|---|---|---|---|---|---|---|---|---|")
for nm,size,cap in CAND:
    A=[];B=[];U=[];N=[]
    for s in range(60):
        e1,m1,u1,c1=sim2(sz(size),sz(cap),*IS,s); e2,m2,u2,c2=sim2(sz(size),sz(cap),*OS,s)
        A.append((((e1/100)**(1/YIS)-1)*100,m1)); B.append((((e2/100)**(1/YOS)-1)*100,m2))
        U.append(np.concatenate([u1,u2])); N.append(np.concatenate([c1,c2]))
    A=np.array(A);B=np.array(B);U=np.concatenate(U);N=np.concatenate(N)
    expo=sum(size[k]*cap[k] for k in ORDER)
    print(f"| {nm} | {expo}% | {A[:,0].mean():+.1f}% | {A[:,1].mean():.0f}% | **{B[:,0].mean():+.1f}%** | {B[:,1].mean():.0f}% | "
          f"{np.median(U):.0f}% | {np.percentile(U,90):.0f}% | {N.mean():.1f}종목 |")
