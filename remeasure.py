# -*- coding: utf-8 -*-
"""여섯 규칙 전면 재측정
   (1) 중복 신호 제거 — 보유 중인 종목은 재진입 불가 (실제로 잡을 수 있는 거래만)
   (2) 생존편향 크기 산정 — 업종 조건이 폐지종목을 몇 건이나 '평가조차 안 했나'
"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
K=pd.read_pickle("data/kp_hz2.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
Q=pd.read_pickle("data/kq_hz2.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
for D,hs in ((K,(5,40)),(Q,(20,40))):
    g=D.groupby("ticker",sort=False)
    for h in hs: D[f"lo{h}"]=g.low.shift(-1).rolling(h,min_periods=1).min().shift(-(h-1))
gk=K.groupby("ticker",sort=False)
K["ret250"]=gk.close.transform(lambda x:x/x.shift(250)-1)*100
K["above20"]=gk.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
R={}
R["P1"]=(K,((K.fromhi>=-10)&(K.r16<120)&(K.rw1<=120)&(K.fw5>=3)&(K.fw60>=1)&(K.vol20<=2)&(K.sr20<=0.5)
        &(K.ret20<=5)&(K.amt20>=200)&(~K.dil)).fillna(False)&~((K.above20>70)&(K.ret250>120)).fillna(False),40,15,None)
R["P2"]=(K,((K.r16<30)&(K.rw1>=200)&(K.fw5>=2)&(K.amt>=3)&(K.ret3<=-5)&(K.ret10<=0)&(~K.k20)&(K.srd==True)&(~K.dil)).fillna(False),10,None,None)
R["P3"]=(K,((K.ret20<=-20)&(K.su1>=2)&(K.fw60>=1)&(K.amt20>=3)&(~K.k60)&(K.srd==True)&(~K.dil)&K.u.notna()&(K.u<=-10)).fillna(False),20,None,
         ((K.ret20<=-20)&(K.su1>=2)&(K.fw60>=1)&(K.amt20>=3)&(~K.k60)&(K.srd==True)&(~K.dil)).fillna(False))
R["P4"]=(K,((K.u<=-20)&(K.dma20<=-10)&(K.srd==True)&K.ok).fillna(False),5,15,
         ((K.dma20<=-10)&(K.srd==True)&K.ok).fillna(False))
R["D1"]=(Q,((Q.ret20<=-20)&(Q.su1>=2)&(Q.fw60>=1)&(Q.amt20>=2)&(~Q.k60)&(Q.srd==True)&(~Q.dil)&(Q.close>=1000)
        &(Q.ow20>=0)&Q.u.notna()&(Q.u<=-20)&(Q.부채비율.fillna(0)<=200)).fillna(False),20,None,
         ((Q.ret20<=-20)&(Q.su1>=2)&(Q.fw60>=1)&(Q.amt20>=2)&(~Q.k60)&(Q.srd==True)&(~Q.dil)&(Q.close>=1000)
        &(Q.ow20>=0)&(Q.부채비율.fillna(0)<=200)).fillna(False))
R["D2"]=(Q,(((Q.close>=1000)&(~Q.dil)&(Q.amt20>=5)&(Q.PBR<=0.5)&(Q.srd==True)&(Q.ret20<=-10)
        &(Q.u<=-10)&(Q.su1>=2)&(~Q.k60)&(Q.ow20>=0))).fillna(False),40,None,
         (((Q.close>=1000)&(~Q.dil)&(Q.amt20>=5)&(Q.PBR<=0.5)&(Q.srd==True)&(Q.ret20<=-10)
        &(Q.su1>=2)&(~Q.k60)&(Q.ow20>=0))).fillna(False))
NM={"P1":"P1 조용한 신고가","P2":"P2 조정매집","P3":"P3 폭락반등","P4":"P4 업종붕괴 이탈","D1":"D1 낙폭과대","D2":"D2 저PBR 낙폭"}
dates={"K":sorted(K.date.unique()),"Q":sorted(Q.date.unique())}
DI={k:{d:i for i,d in enumerate(v)} for k,v in dates.items()}
OUT={}
for k,(D,m,h,stop,nou) in R.items():
    mk="K" if D is K else "Q"
    X=D[m].copy()
    r=X[f"n{h}"].values.astype(float)
    if stop:
        hit=((X[f"lo{h}"]/X.buy-1)*100<=-stop).values
        r=np.where(hit,-stop-X.cost.values,r)
    X["r"]=r; X=X.dropna(subset=["r"]).copy()
    X["di"]=X.date.map(DI[mk])
    # 보유 중 재진입 금지 = 같은 종목 h거래일 내 재신호 제외
    keep=[];last={}
    for row in X.sort_values("di").itertuples():
        if row.ticker in last and row.di-last[row.ticker]<h: continue
        last[row.ticker]=row.di; keep.append(row.Index)
    OUT[k]=(X,X.loc[keep],h,nou,D)
print("# 중복 신호 제거 재측정 (보유 중 재진입 금지)\n")
print("| 규칙 | 보유 | 원본 건수 | **실거래 건수** | 원본 검증 | **실거래 검증** | 승률 | PF | 학습 |")
print("|---|---|---|---|---|---|---|---|---|")
for k,(X,Y,h,nou,D) in OUT.items():
    a=X[X.y>=2023].r; b=Y[Y.y>=2023].r
    la=Y[Y.y<=2022].r
    r=b.values; pf=r[r>0].sum()/abs(r[r<=0].sum()) if (r<=0).any() else 99
    print(f"| {NM[k]} | {h}일 | {len(X):,} | **{len(Y):,}** ({len(Y)/len(X)*100:.0f}%) | {a.mean():+.2f}% | **{b.mean():+.2f}%** | {(r>0).mean()*100:.0f}% | {pf:.2f} | {la.mean():+.2f}% |")
print("\n# 생존편향 — 업종 조건이 폐지종목을 평가조차 안 한 규모\n")
print("| 규칙 | 신호 중 폐지 | 업종조건 뺐을 때 폐지 통과 | **미평가 비중** |")
print("|---|---|---|---|")
for k,(X,Y,h,nou,D) in OUT.items():
    if nou is None: print(f"| {NM[k]} | {int((X.grp=='폐지').sum())}건 | 업종조건 미사용 | — |"); continue
    z=D[nou]; zd=int((z.grp=="폐지").sum())
    print(f"| {NM[k]} | {int((X.grp=='폐지').sum())}건 | **{zd:,}건** | {zd/max(len(z),1)*100:.1f}% |")
import pickle; pickle.dump({k:(v[1],v[2]) for k,v in OUT.items()},open("data/dedup_trades.pkl","wb"))
print("\n연도별 (실거래 기준)\n")
YS=list(range(2018,2027))
print("| 규칙 | "+" | ".join(str(y) for y in YS)+" |\n|---|"+"---|"*len(YS))
for k,(X,Y,h,nou,D) in OUT.items():
    c=[]
    for y in YS:
        s=Y[Y.y==y]
        c.append(f"{s.r.mean():+.1f}%<br>{len(s)}건" if len(s)>=3 else (f"{len(s)}건" if len(s) else "—"))
    print(f"| {NM[k]} | "+" | ".join(c)+" |")
