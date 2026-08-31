# -*- coding: utf-8 -*-
"""비중·보유기간 그리드 — 낙폭을 낮추면서 수익을 지키는 조합 찾기"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
K=pd.read_pickle("data/kp_hz2.pkl"); Q=pd.read_pickle("data/kq_hz.pkl")
g=K.groupby("ticker",sort=False)
K["ret250"]=g.close.transform(lambda x:x/x.shift(250)-1)*100
K["above20"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
EX={"P1":(K,((K.fromhi>=-10)&(K.r16<120)&(K.rw1<=120)&(K.fw5>=3)&(K.fw60>=1)&(K.vol20<=2)&(K.sr20<=0.5)
        &(K.ret20<=5)&(K.amt20>=200)&(~K.dil)).fillna(False)&~((K.above20>70)&(K.ret250>120)).fillna(False),40),
 "P2":(K,((K.r16<30)&(K.rw1>=200)&(K.fw5>=2)&(K.amt>=3)&(K.ret3<=-5)&(K.ret10<=0)&(~K.k20)&(K.srd==True)&(~K.dil)).fillna(False),10),
 "P3":(K,((K.ret20<=-20)&(K.su1>=2)&(K.fw60>=1)&(K.amt20>=3)&(~K.k60)&(K.srd==True)&(~K.dil)&K.u.notna()&(K.u<=-10)).fillna(False),20),
 "D1":(Q,((Q.ret20<=-20)&(Q.su1>=2)&(Q.fw60>=1)&(Q.amt20>=2)&(~Q.k60)&(Q.srd==True)&(~Q.dil)&(Q.close>=1000)
        &(Q.ow20>=0)&Q.u.notna()&(Q.u<=-20)&(Q.부채비율.fillna(0)<=200)).fillna(False),20),
 "D2":(Q,(((Q.close>=1000)&(~Q.dil)&(Q.amt20>=5)&(Q.PBR<=0.5)&(Q.srd==True)&(Q.ret20<=-10)
        &(Q.u<=-10)&(Q.su1>=2)&(~Q.k60)&(Q.ow20>=0))).fillna(False),40)}
base=[]
for r,(D,mm,h) in EX.items():
    s=D[mm].copy(); s["R"]=r; s["hold"]=h; s["r"]=s[f"n{h}"]
    base.append(s[["R","date","ticker","y","r","hold"]].dropna(subset=["r"]))
BASE=pd.concat(base,ignore_index=True)
NEWM=((K.u<=-20)&(K.dma20<=-10)&(K.srd==True)&K.ok).fillna(False)
def newtr(h):
    s=K[NEWM].copy(); s["R"]="NEW"; s["hold"]=h; s["r"]=s[f"n{h}"]
    return s[["R","date","ticker","y","r","hold"]].dropna(subset=["r"])
SIZE0={"P1":12,"P2":15,"P3":5,"D1":5,"D2":5}; CAP0={"P1":7,"P2":2,"P3":3,"D1":3,"D2":3}
def sim(T,size,cap,d0,d1,seed):
    rng=np.random.default_rng(seed)
    dates=sorted(T.date.unique()); DI={d:i for i,d in enumerate(dates)}
    sig={}
    for r in T.itertuples(): sig.setdefault(r.date,[]).append((r.R,r.ticker,float(r.r),int(r.hold)))
    cash=100.0;held=[];peak=100.0;mdd=0.0;n=0
    i0=next(i for i,d in enumerate(dates) if d>=d0); i1=max(i for i,d in enumerate(dates) if d<=d1)
    for i in range(i0,i1+1):
        keep=[]
        for hh in held:
            if hh["out"]<=i: cash+=hh["amt"]*(1+hh["r"]/100); n+=1
            else: keep.append(hh)
        held=keep; eq=cash+sum(h["amt"] for h in held)
        s=sig.get(dates[i],[])
        for j in rng.permutation(len(s)):
            R,tk,rr,hd=s[j]
            if sum(1 for h in held if h["R"]==R)>=cap[R]: continue
            if any(h["tk"]==tk for h in held): continue
            a=eq*size[R]/100
            if a>cash: continue
            held.append(dict(R=R,tk=tk,amt=a,r=rr,out=i+hd)); cash-=a
        eq=cash+sum(h["amt"] for h in held); peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak*100)
    eq=cash+sum(h["amt"]*(1+h["r"]/100) for h in held)
    return eq,mdd,n
def run(T,size,cap,seeds=40):
    o=[]
    for s in range(seeds):
        e1,m1,_=sim(T,size,cap,"20180101","20221231",s); e2,m2,n2=sim(T,size,cap,"20230101","20260831",s)
        o.append((((e1/100)**(1/5)-1)*100,m1,((e2/100)**(1/3.66)-1)*100,m2,n2))
    return np.array(o)
print("## 비중·보유기간 그리드 (계좌 100 · 40시드)\n")
print("| 신규 규칙 설정 | 학습 연평균 | 학습MDD | **검증 연평균** | **검증MDD** | 검증 거래 | 수익/낙폭 |")
print("|---|---|---|---|---|---|---|")
o=run(BASE,SIZE0,CAP0)
print(f"| 없음 (현재 5규칙) | {o[:,0].mean():+.1f}% | {o[:,1].mean():.0f}% | **{o[:,2].mean():+.1f}%** | **{o[:,3].mean():.0f}%** | {o[:,4].mean():.0f}건 | {o[:,2].mean()/max(o[:,3].mean(),1):.2f} |")
for hold in (3,4,5,10):
    T=pd.concat([BASE,newtr(hold)],ignore_index=True)
    for sz,cp in ((8,6),(5,4),(5,3),(4,5),(3,4)):
        size={**SIZE0,"NEW":sz}; cap={**CAP0,"NEW":cp}
        o=run(T,size,cap)
        print(f"| {hold}일 · 종목당 {sz} · 최대 {cp}종목 (노출 {sz*cp}) | {o[:,0].mean():+.1f}% | {o[:,1].mean():.0f}% | **{o[:,2].mean():+.1f}%** | **{o[:,3].mean():.0f}%** | {o[:,4].mean():.0f}건 | {o[:,2].mean()/max(o[:,3].mean(),1):.2f} |")
