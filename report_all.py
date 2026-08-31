# -*- coding: utf-8 -*-
"""여섯 규칙 연도별 건수·수익률·수익금 (신호당 100만원)"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
CASH=1_000_000
K=pd.read_pickle("data/kp_hz2.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
Q=pd.read_pickle("data/kq_hz2.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
for D,hs in ((K,(5,40)),(Q,(20,40))):
    g=D.groupby("ticker",sort=False)
    for h in hs:
        D[f"lo{h}"]=g.low.shift(-1).rolling(h,min_periods=1).min().shift(-(h-1))
gk=K.groupby("ticker",sort=False)
K["ret250"]=gk.close.transform(lambda x:x/x.shift(250)-1)*100
K["above20"]=gk.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
R={}
R["P1"]=(K,((K.fromhi>=-10)&(K.r16<120)&(K.rw1<=120)&(K.fw5>=3)&(K.fw60>=1)&(K.vol20<=2)&(K.sr20<=0.5)
        &(K.ret20<=5)&(K.amt20>=200)&(~K.dil)).fillna(False)&~((K.above20>70)&(K.ret250>120)).fillna(False),40,15)
R["P2"]=(K,((K.r16<30)&(K.rw1>=200)&(K.fw5>=2)&(K.amt>=3)&(K.ret3<=-5)&(K.ret10<=0)&(~K.k20)&(K.srd==True)&(~K.dil)).fillna(False),10,None)
R["P3"]=(K,((K.ret20<=-20)&(K.su1>=2)&(K.fw60>=1)&(K.amt20>=3)&(~K.k60)&(K.srd==True)&(~K.dil)&K.u.notna()&(K.u<=-10)).fillna(False),20,None)
R["P4"]=(K,((K.u<=-20)&(K.dma20<=-10)&(K.srd==True)&K.ok).fillna(False),5,15)
R["D1"]=(Q,((Q.ret20<=-20)&(Q.su1>=2)&(Q.fw60>=1)&(Q.amt20>=2)&(~Q.k60)&(Q.srd==True)&(~Q.dil)&(Q.close>=1000)
        &(Q.ow20>=0)&Q.u.notna()&(Q.u<=-20)&(Q.부채비율.fillna(0)<=200)).fillna(False),20,None)
R["D2"]=(Q,(((Q.close>=1000)&(~Q.dil)&(Q.amt20>=5)&(Q.PBR<=0.5)&(Q.srd==True)&(Q.ret20<=-10)
        &(Q.u<=-10)&(Q.su1>=2)&(~Q.k60)&(Q.ow20>=0))).fillna(False),40,None)
NM={"P1":"P1 조용한 신고가","P2":"P2 조정매집","P3":"P3 폭락반등","P4":"P4 업종붕괴 이탈",
    "D1":"D1 낙폭과대","D2":"D2 저PBR 낙폭"}
T={}
for k,(D,m,h,stop) in R.items():
    X=D[m].copy()
    r=X[f"n{h}"].values.astype(float)
    if stop:
        hit=((X[f"lo{h}"]/X.buy-1)*100<=-stop).values
        r=np.where(hit,-stop-X.cost.values,r)
    X["r"]=r; X=X.dropna(subset=["r"])
    X["pnl"]=X.r/100*CASH
    T[k]=X[["date","ticker","name","y","r","pnl"]]
YS=list(range(2018,2027))
print("# 규칙별 연도별 성적 (신호당 100만원 · 손절 P1·P4 -15% 적용)\n")
print("## 1) 발생 건수\n")
print("| 규칙 | "+" | ".join(str(y) for y in YS)+" | **합계** |")
print("|---|"+"---|"*(len(YS)+1))
for k in NM:
    c=[str(len(T[k][T[k].y==y])) if len(T[k][T[k].y==y]) else "—" for y in YS]
    print(f"| {NM[k]} | "+" | ".join(c)+f" | **{len(T[k]):,}** |")
tot=[sum(len(T[k][T[k].y==y]) for k in NM) for y in YS]
print("| **전체** | "+" | ".join(f"**{x:,}**" if x else "—" for x in tot)+f" | **{sum(tot):,}** |")
print("\n## 2) 연도별 평균 수익률 (건당)\n")
print("| 규칙 | "+" | ".join(str(y) for y in YS)+" | **전체평균** |")
print("|---|"+"---|"*(len(YS)+1))
for k in NM:
    c=[]
    for y in YS:
        s=T[k][T[k].y==y]
        c.append(f"{s.r.mean():+.1f}%" if len(s) else "—")
    print(f"| {NM[k]} | "+" | ".join(c)+f" | **{T[k].r.mean():+.2f}%** |")
print("\n## 3) 연도별 수익금 (신호당 100만원, 만원 단위)\n")
print("| 규칙 | "+" | ".join(str(y) for y in YS)+" | **합계** |")
print("|---|"+"---|"*(len(YS)+1))
for k in NM:
    c=[]
    for y in YS:
        s=T[k][T[k].y==y]
        c.append(f"{s.pnl.sum()/1e4:+,.0f}" if len(s) else "—")
    print(f"| {NM[k]} | "+" | ".join(c)+f" | **{T[k].pnl.sum()/1e4:+,.0f}만** |")
yt=[sum(T[k][T[k].y==y].pnl.sum() for k in NM) for y in YS]
print("| **전체** | "+" | ".join(f"**{x/1e4:+,.0f}**" if x else "—" for x in yt)+f" | **{sum(yt)/1e4:+,.0f}만** |")
print("\n## 4) 연도별 투입금액 대비 수익률 (그 해 투입액 = 건수 × 100만원)\n")
print("| 규칙 | "+" | ".join(str(y) for y in YS)+" |")
print("|---|"+"---|"*len(YS))
for k in NM:
    c=[]
    for y in YS:
        s=T[k][T[k].y==y]
        c.append(f"{s.r.mean():+.1f}%" if len(s) else "—")
    print(f"| {NM[k]} | "+" | ".join(c)+" |")
inv=[x*CASH for x in tot]
print("| **전체 투입** | "+" | ".join(f"{x/1e8:.1f}억" if x else "—" for x in inv)+" |")
print("| **전체 수익률** | "+" | ".join(f"**{yt[i]/inv[i]*100:+.1f}%**" if inv[i] else "—" for i in range(len(YS)))+" |")
print(f"\n전체기간 총 투입 {sum(inv)/1e8:.1f}억 · 총 수익 {sum(yt)/1e8:.2f}억 · 수익률 {sum(yt)/sum(inv)*100:+.2f}%")
print("\n## 5) 학습/검증 구분\n")
print("| 규칙 | 학습(2018~22) 건수 | 학습 건당 | 검증(2023~26) 건수 | **검증 건당** | 검증 수익금 |")
print("|---|---|---|---|---|---|")
for k in NM:
    a=T[k][T[k].y<=2022]; b=T[k][T[k].y>=2023]
    print(f"| {NM[k]} | {len(a):,} | {a.r.mean():+.2f}% | {len(b):,} | **{b.r.mean():+.2f}%** | {b.pnl.sum()/1e4:+,.0f}만 |")
A=pd.concat(T.values()); Ab=A[A.y>=2023]
print(f"| **전체** | {len(A[A.y<=2022]):,} | {A[A.y<=2022].r.mean():+.2f}% | {len(Ab):,} | **{Ab.r.mean():+.2f}%** | {Ab.pnl.sum()/1e4:+,.0f}만 |")
