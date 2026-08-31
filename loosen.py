# -*- coding: utf-8 -*-
"""규칙별 조건 완화 탐색 — 건수를 늘리면서 성적이 얼마나 상하는가
   실거래(중복 제거) 기준 · 월단위 신뢰구간 포함
"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
K=pd.read_pickle("data/kp_hz2.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
Q=pd.read_pickle("data/kq_hz2.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
for D in (K,Q):
    g=D.groupby("ticker",sort=False)
    D["hi60"]=g.close.transform(lambda x:x.rolling(60,min_periods=30).max())
    D["dd"]=(D.close/D.hi60-1)*100
    D["mdd60"]=g["dd"].transform(lambda x:x.rolling(60,min_periods=30).min())
    for h in (5,10,20,40):
        D[f"lo{h}"]=g.low.shift(-1).rolling(h,min_periods=1).min().shift(-(h-1))
    dates=sorted(D.date.unique()); DI={d:i for i,d in enumerate(dates)}
    D["di"]=D.date.map(DI)
gk=K.groupby("ticker",sort=False)
K["ret250"]=gk.close.transform(lambda x:x/x.shift(250)-1)*100
K["above20"]=gk.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
rng=np.random.default_rng(808)
def ev(D,M,h,stop,base_n=None):
    X=D[M.fillna(False)].copy()
    if len(X)<30: return None
    r=X[f"n{h}"].values.astype(float)
    if stop:
        hit=((X[f"lo{h}"]/X.buy-1)*100<=-stop).values
        r=np.where(hit,-stop-X.cost.values,r)
    X["r"]=r; X=X.dropna(subset=["r"])
    keep=[];last={}
    for row in X.sort_values("di").itertuples():
        if row.ticker in last and row.di-last[row.ticker]<h: continue
        last[row.ticker]=row.di; keep.append(row.Index)
    Y=X.loc[keep].copy(); Y["ym"]=Y.date.str[:6]
    a=Y[Y.y<=2022].r.values; b=Y[Y.y>=2023]; rr=b.r.values
    if len(rr)<15: return None
    pf=rr[rr>0].sum()/abs(rr[rr<=0].sum()) if (rr<=0).any() else 99
    mo=[list(x) for _,x in b.groupby("ym").r]; mo=[x for x in mo if x]
    bs=np.array([np.mean([v for i in rng.integers(0,len(mo),len(mo)) for v in mo[i]]) for _ in range(900)])
    lo,hi=np.percentile(bs,2.5),np.percentile(bs,97.5)
    return dict(n=len(Y),vn=len(rr),ism=a.mean() if len(a) else np.nan,m=rr.mean(),md=np.median(rr),
                w=(rr>0).mean()*100,pf=pf,lo=lo,hi=hi,mon=len(rr)/44,months=b.ym.nunique())
def show(D,title,base,variants,h,stop):
    print(f"\n## {title}\n")
    print("| 조건 완화 | 실거래 | 검증건수 | **월평균** | 학습 | **검증** | 중앙값 | 승률 | PF | **월단위 95%** |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    b0=ev(D,base,h,stop)
    def line(lab,s):
        if not s: print(f"| {lab} | — | | | | 표본부족 | | | | |"); return
        mk="**" if s['lo']>0 else ""
        mul=f" ×{s['vn']/b0['vn']:.1f}" if b0 and lab!="현행" else ""
        print(f"| {lab} | {s['n']:,} | {s['vn']}{mul} | **{s['mon']:.1f}건** | {s['ism']:+.2f}% | **{s['m']:+.2f}%** | {s['md']:+.2f}% | {s['w']:.0f}% | {s['pf']:.2f} | {mk}{s['lo']:+.1f}~{s['hi']:+.1f}%{mk} |")
    line("현행",b0)
    for lab,M in variants: line(lab,ev(D,M,h,stop))
# ── P1 ──────────────────────────────────────────────────────
P1=((K.fromhi>=-10)&(K.r16<120)&(K.rw1<=120)&(K.fw5>=3)&(K.fw60>=1)&(K.vol20<=2)&(K.sr20<=0.5)
    &(K.ret20<=5)&(K.amt20>=200)&(~K.dil)).fillna(False)&~((K.above20>70)&(K.ret250>120)).fillna(False)
def p1(**o):
    return (((K.fromhi>=o.get("fromhi",-10))&(K.r16<o.get("r16",120))&(K.rw1<=o.get("rw1",120))
      &(K.fw5>=o.get("fw5",3))&(K.fw60>=o.get("fw60",1))&(K.vol20<=o.get("vol",2))&(K.sr20<=o.get("sr",0.5))
      &(K.ret20<=o.get("ret20",5))&(K.amt20>=o.get("amt",200))&(~K.dil)).fillna(False)
      &~((K.above20>70)&(K.ret250>120)).fillna(False))
show(K,"P1 조용한 신고가 (40일·손절15%)",P1,[
 ("신고가 -10 → -15%",p1(fromhi=-15)),("신고가 -10 → -20%",p1(fromhi=-20)),
 ("변동성 2 → 2.5%",p1(vol=2.5)),("변동성 2 → 3%",p1(vol=3)),
 ("공매도 0.5 → 1%",p1(sr=1)),("20일수익 5 → 10%",p1(ret20=10)),
 ("거래대금 200 → 100억",p1(amt=100)),("거래대금 200 → 50억",p1(amt=50)),
 ("외인5일 3 → 1%",p1(fw5=1)),
 ("완화 묶음(변동2.5·공매도1·거래대금100)",p1(vol=2.5,sr=1,amt=100)),
],40,15)
# ── P2 ──────────────────────────────────────────────────────
def p2(**o):
    return ((K.r16<o.get("r16",30))&(K.rw1>=o.get("rw1",200))&(K.fw5>=o.get("fw5",2))&(K.amt>=o.get("amt",3))
      &(K.ret3<=o.get("ret3",-5))&(K.ret10<=o.get("ret10",0))&(~K.k20)&(K.srd==True)&(~K.dil)).fillna(False)
show(K,"P2 조정매집 (10일)",p2(),[
 ("거래량침체 30 → 50",p2(r16=50)),("거래량침체 30 → 80",p2(r16=80)),
 ("급증 200 → 150",p2(rw1=150)),("3일수익 -5 → -3%",p2(ret3=-3)),
 ("외인5일 2 → 1%",p2(fw5=1)),("10일수익 0 → 5%",p2(ret10=5)),
 ("완화 묶음(침체50·급증150·3일-3)",p2(r16=50,rw1=150,ret3=-3)),
],10,None)
# ── P3 ──────────────────────────────────────────────────────
def p3(**o):
    return ((K.ret20<=o.get("ret20",-20))&(K.su1>=o.get("su1",2))&(K.fw60>=o.get("fw60",1))
      &(K.amt20>=o.get("amt",3))&(~K.k60)&(K.srd==True)&(~K.dil)&K.u.notna()&(K.u<=o.get("u",-10))).fillna(False)
show(K,"P3 폭락반등 (20일)",p3(),[
 ("20일수익 -20 → -15%",p3(ret20=-15)),("20일수익 -20 → -10%",p3(ret20=-10)),
 ("거래량 2 → 1.5배",p3(su1=1.5)),("업종 -10 → -5%",p3(u=-5)),("업종 -10 → 0%",p3(u=0)),
 ("외인60일 1 → 0%",p3(fw60=0)),("거래대금 3 → 1억",p3(amt=1)),
 ("완화 묶음(20일-15·거래량1.5·업종-5)",p3(ret20=-15,su1=1.5,u=-5)),
],20,None)
# ── D1 ──────────────────────────────────────────────────────
def d1(**o):
    return ((Q.ret20<=o.get("ret20",-20))&(Q.su1>=o.get("su1",2))&(Q.fw60>=o.get("fw60",1))&(Q.amt20>=o.get("amt",2))
      &(~Q.k60)&(Q.srd==True)&(~Q.dil)&(Q.close>=1000)&(Q.ow20>=o.get("ow",0))
      &Q.u.notna()&(Q.u<=o.get("u",-20))&(Q.부채비율.fillna(0)<=o.get("dbt",200))).fillna(False)
show(Q,"D1 낙폭과대 (20일)",d1(),[
 ("20일수익 -20 → -15%",d1(ret20=-15)),("업종 -20 → -15%",d1(u=-15)),("업종 -20 → -10%",d1(u=-10)),
 ("외인60일 1 → 0%",d1(fw60=0)),("기관 0 → -1%",d1(ow=-1)),("거래량 2 → 1.5배",d1(su1=1.5)),
 ("부채 200 → 300%",d1(dbt=300)),
 ("완화 묶음(업종-15·20일-15·거래량1.5)",d1(u=-15,ret20=-15,su1=1.5)),
],20,None)
# ── D2 ──────────────────────────────────────────────────────
def d2(**o):
    return ((Q.close>=1000)&(~Q.dil)&(Q.amt20>=o.get("amt",5))&(Q.PBR<=o.get("pbr",0.5))&(Q.srd==True)
      &(Q.ret20<=o.get("ret20",-10))&(Q.u<=o.get("u",-10))&(Q.su1>=o.get("su1",2))&(~Q.k60)&(Q.ow20>=o.get("ow",0))).fillna(False)
show(Q,"D2 저PBR 낙폭 (40일)",d2(),[
 ("PBR 0.5 → 0.7",d2(pbr=0.7)),("PBR 0.5 → 1.0",d2(pbr=1.0)),
 ("20일수익 -10 → -5%",d2(ret20=-5)),("업종 -10 → -5%",d2(u=-5)),
 ("거래량 2 → 1.5배",d2(su1=1.5)),("거래대금 5 → 2억",d2(amt=2)),
 ("완화 묶음(PBR0.7·거래량1.5·업종-5)",d2(pbr=0.7,su1=1.5,u=-5)),
],40,None)
