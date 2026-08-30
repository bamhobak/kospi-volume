# -*- coding: utf-8 -*-
"""재무 조건을 기존 4규칙에 얹었을 때 — 학습·검증 둘 다 개선돼야 채택"""
import io,sys,csv,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
K=pd.read_pickle("data/kp_all.pkl"); Q=pd.read_pickle("data/kq_all.pkl")
IND={}
for r in csv.DictReader(open("data/industry.csv",encoding="utf-8-sig")):
    k=list(r.values()); IND[k[0]]=k[-1]
def addu(D):
    D=D.copy(); D["up"]=D.ticker.map(IND)
    d=D[D.up.notna()].dropna(subset=["ret60"]); g=d.groupby(["date","up"]).ret60
    m=g.median(); c=g.size(); m=m[c>=5]
    D["u"]=pd.MultiIndex.from_arrays([D.date,D.up]).map(m); return D
K=addu(K); Q=addu(Q)
g=K.groupby("ticker",sort=False)
K["ret250"]=g.close.transform(lambda x:x/x.shift(250)-1)*100
K["above20"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
RULES={
 "P1":(K,((K.fromhi>=-10)&(K.r16<120)&(K.rw1<=120)&(K.fw5>=3)&(K.fw60>=1)&(K.vol20<=2)&(K.sr20<=0.5)
        &(K.ret20<=5)&(K.amt20>=200)&(~K.dil)).fillna(False)&~((K.above20>70)&(K.ret250>120)).fillna(False),40),
 "P2":(K,((K.r16<30)&(K.rw1>=200)&(K.fw5>=2)&(K.amt>=3)&(K.ret3<=-5)&(K.ret10<=0)&(~K.k20)&(K.srd==True)&(~K.dil)).fillna(False),10),
 "P3":(K,((K.ret20<=-20)&(K.su1>=2)&(K.fw60>=1)&(K.amt20>=3)&(~K.k60)&(K.srd==True)&(~K.dil)&K.u.notna()&(K.u<=-10)).fillna(False),20),
 "D1":(Q,((Q.ret20<=-20)&(Q.su1>=2)&(Q.fw60>=1)&(Q.amt20>=2)&(~Q.k60)&(Q.srd==True)&(~Q.dil)&(Q.close>=1000)
        &(Q.ow20>=0)&Q.u.notna()&(Q.u<=-20)).fillna(False),20)}
def S(r):
    r=np.asarray(r)
    if len(r)<8: return None
    pf=r[r>0].sum()/abs(r[r<=0].sum()) if (r<=0).any() else 99
    return len(r),r.mean(),np.median(r),(r>0).mean()*100,pf,r.min()
for nm,(D,base,h) in RULES.items():
    X=D[base]
    print(f"\n## {nm} 에 재무 조건 추가 (기준 {len(X)}건)\n")
    print("| 재무 조건 | 건수 | 보존 | 학습 | **검증** | 중앙값 | 승률 | PF | 최악 |\n|---|---|---|---|---|---|---|---|---|")
    C=[("없음",pd.Series(True,index=X.index))]
    C+=[("자본잠식 제외",X.자본잠식!=1),("적자 제외(ROE>0)",X.ROE>0),
        ("영업적자 제외",X.영업이익률>0),("부채비율 ≤ 200%",X.부채비율<=200),
        ("부채비율 ≤ 100%",X.부채비율<=100),("자기자본비율 ≥ 30%",X.자본자산>=30),
        ("매출성장 ≥ 0%",X.매출성장>=0),("영업이익성장 ≥ 0%",X.영업이익성장>=0),
        ("재무 데이터 있음",X.ROE.notna()),
        ("자본잠식제외+영업흑자",(X.자본잠식!=1)&(X.영업이익률>0))]
    n0=len(X)
    for cn,m in C:
        m=m.fillna(True) if cn!="재무 데이터 있음" else m.fillna(False)
        s=X[m]
        a=S(s[s.y<=2022][f"n{h}"].dropna()); b=S(s[s.y>=2023][f"n{h}"].dropna())
        if not b: continue
        print(f"| {cn} | {len(s)} | {len(s)/n0*100:.0f}% | {a[1] if a else float('nan'):+.2f}% | **{b[1]:+.2f}%** | {b[2]:+.2f}% | {b[3]:.0f}% | {b[4]:.2f} | {b[5]:.0f}% |")
