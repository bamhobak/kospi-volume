# -*- coding: utf-8 -*-
"""후보 최종 검증 — 기존 규칙 중복 · 포트폴리오 영향 · 연도별"""
import io,sys,pickle,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
K=pd.read_pickle("data/kp_hz.pkl"); Q=pd.read_pickle("data/kq_hz.pkl")
g=K.groupby("ticker",sort=False)
K["ret250"]=g.close.transform(lambda x:x/x.shift(250)-1)*100
K["above20"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
EX={
 "P1":(K,((K.fromhi>=-10)&(K.r16<120)&(K.rw1<=120)&(K.fw5>=3)&(K.fw60>=1)&(K.vol20<=2)&(K.sr20<=0.5)
        &(K.ret20<=5)&(K.amt20>=200)&(~K.dil)).fillna(False)&~((K.above20>70)&(K.ret250>120)).fillna(False)),
 "P2":(K,((K.r16<30)&(K.rw1>=200)&(K.fw5>=2)&(K.amt>=3)&(K.ret3<=-5)&(K.ret10<=0)&(~K.k20)&(K.srd==True)&(~K.dil)).fillna(False)),
 "P3":(K,((K.ret20<=-20)&(K.su1>=2)&(K.fw60>=1)&(K.amt20>=3)&(~K.k60)&(K.srd==True)&(~K.dil)&K.u.notna()&(K.u<=-10)).fillna(False)),
 "D1":(Q,((Q.ret20<=-20)&(Q.su1>=2)&(Q.fw60>=1)&(Q.amt20>=2)&(~Q.k60)&(Q.srd==True)&(~Q.dil)&(Q.close>=1000)
        &(Q.ow20>=0)&Q.u.notna()&(Q.u<=-20)&(Q.부채비율.fillna(0)<=200)).fillna(False)),
 "D2":(Q,(((Q.close>=1000)&(~Q.dil)&(Q.amt20>=5)&(Q.PBR<=0.5)&(Q.srd==True)&(Q.ret20<=-10)
        &(Q.u<=-10)&(Q.su1>=2)&(~Q.k60)&(Q.ow20>=0))).fillna(False))}
CAND={
 "A 회전율":(K.u<=-20)&(K.dma20<=-10)&(K.srd==True)&(K.회전율>=0.5),
 "B 최소":(K.u<=-20)&(K.dma20<=-10)&(K.srd==True),
 "C ROE":(K.u<=-20)&(K.dma20<=-10)&(K.ROE>=0)&(K.srd==True)}
print("## 1) 기존 규칙과 신호 중복 (코스피 후보 · 5일 보유)\n")
print("| 후보 | 전체 | P1 | P2 | P3 | 겹침 합계 |\n|---|---|---|---|---|---|")
for nm,m in CAND.items():
    X=K[(m&K.ok).fillna(False)]
    sx=set(zip(X.date,X.ticker)); row=[]
    tot=set()
    for r in ("P1","P2","P3"):
        D,mm=EX[r]; sy=set(zip(D[mm].date,D[mm].ticker))
        row.append(f"{len(sx&sy)}"); tot|=(sx&sy)
    print(f"| {nm} | {len(sx):,} | "+" | ".join(row)+f" | **{len(tot)}건 ({len(tot)/len(sx)*100:.1f}%)** |")
print("\n## 2) 연도별 (5일 보유, 검증 굵게)\n")
YS=list(range(2018,2027))
print("| 후보 | "+" | ".join(str(y) for y in YS)+" |\n|---|"+"---|"*len(YS))
for nm,m in CAND.items():
    X=K[(m&K.ok).fillna(False)]; c=[]
    for y in YS:
        s=X[X.y==y].n5.dropna()
        c.append(f"{s.mean():+.1f}%<br>{len(s)}건" if len(s)>=3 else (f"{len(s)}건" if len(s) else "—"))
    print(f"| {nm} | "+" | ".join(c)+" |")
print("\n## 3) 월별 신호 분포 (검증기간)\n")
print("| 후보 | 검증건수 | 월평균 | 신호 난 달 | 월 최대 |\n|---|---|---|---|---|")
for nm,m in CAND.items():
    X=K[(m&K.ok).fillna(False)].copy(); X["ym"]=X.date.str[:6]; V=X[X.y>=2023]
    print(f"| {nm} | {len(V):,} | {len(V)/44:.1f}건 | {V.ym.nunique()}/44 | {V.groupby('ym').size().max()}건 |")
# ── 포트폴리오 ─────────────────────────────────────────────
A=pd.read_csv("data/rules_trades_kospi.csv",dtype={"date":str,"ticker":str})
B=pd.read_csv("data/rules_trades_kosdaq.csv",dtype={"date":str,"ticker":str})
for x in (A,B): x.columns=[c.lstrip("\ufeff") for c in x.columns]
base=[]
for r,(D,mm) in EX.items():
    h={"P1":40,"P2":10,"P3":20,"D1":20,"D2":40}[r]
    s=D[mm].copy(); s["R"]=r; s["hold"]=h; s["r"]=s[f"n{h}"]
    base.append(s[["R","date","ticker","y","r","hold"]].dropna(subset=["r"]))
BASE=pd.concat(base,ignore_index=True)
SIZE={"P1":12,"P2":15,"P3":5,"D1":5,"D2":5,"NEW":8}; CAP={"P1":7,"P2":2,"P3":3,"D1":3,"D2":3,"NEW":6}
def sim(T,d0,d1,seed):
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
            if sum(1 for h in held if h["R"]==R)>=CAP[R]: continue
            if any(h["tk"]==tk for h in held): continue
            a=eq*SIZE[R]/100
            if a>cash: continue
            held.append(dict(R=R,tk=tk,amt=a,r=rr,out=i+hd)); cash-=a
        eq=cash+sum(h["amt"] for h in held); peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak*100)
    eq=cash+sum(h["amt"]*(1+h["r"]/100) for h in held)
    return eq,mdd,n
print("\n## 4) 포트폴리오 영향 — 계좌 100 · 신규는 종목당 8 · 최대 6종목 · 40시드\n")
print("| 구성 | 학습 연평균 | 학습MDD | **검증 연평균** | 검증MDD | 검증 거래수 |\n|---|---|---|---|---|---|")
for lab,extra in [("현재 5규칙",None)]+[(f"+ {nm} (5일)",nm) for nm in CAND]:
    T=BASE if extra is None else pd.concat([BASE,
        K[(CAND[extra]&K.ok).fillna(False)].assign(R="NEW",hold=5).rename(columns={"n5":"r"})[["R","date","ticker","y","r","hold"]].dropna(subset=["r"])],ignore_index=True)
    o=[]
    for s in range(40):
        e1,m1,_=sim(T,"20180101","20221231",s); e2,m2,n2=sim(T,"20230101","20260831",s)
        o.append((((e1/100)**(1/5)-1)*100,m1,((e2/100)**(1/3.66)-1)*100,m2,n2))
    o=np.array(o)
    print(f"| {lab} | {o[:,0].mean():+.1f}% | {o[:,1].mean():.0f}% | **{o[:,2].mean():+.1f}%** | {o[:,3].mean():.0f}% | {o[:,4].mean():.0f}건 |")
