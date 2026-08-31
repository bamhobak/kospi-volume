# -*- coding: utf-8 -*-
"""교차 실측
   A. 원웨이 재료(이평선 기준가·되돌림·추세지속)를 우리 규칙에 얹으면 개선되나
   B. 우리 재료(수급·공매도·업종·PBR·재무)를 원웨이에 얹으면 살아나나
"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
def prep(path,amtmin):
    D=pd.read_pickle(path).sort_values(["ticker","date"]).reset_index(drop=True)
    g=D.groupby("ticker",sort=False)
    for w in (5,10):
        D[f"ma{w}"]=g.close.transform(lambda x,w=w:x.rolling(w).mean())
        D[f"dma{w}"]=(D.close/D[f"ma{w}"]-1)*100
    D["hi60"]=g.close.transform(lambda x:x.rolling(60,min_periods=30).max())
    D["lo60"]=g.close.transform(lambda x:x.rolling(60,min_periods=30).min())
    D["fromhi60"]=(D.close/D.hi60-1)*100
    D["fromlo60"]=(D.close/D.lo60-1)*100
    D["dd"]=(D.close/D.hi60-1)*100
    D["mdd60"]=g["dd"].transform(lambda x:x.rolling(60,min_periods=30).min())
    D["above20r"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(60,min_periods=30).mean())*100
    D["ok"]=((D.close>=1000)&(~D.dil)&(D.amt20>=amtmin)).fillna(False)
    dates=sorted(D.date.unique()); DI={x:i for i,x in enumerate(dates)}
    D["di"]=D.date.map(DI)
    lp=g.date.transform("max").map(DI); lc=g.close.transform("last")
    for h in (5,10,20,40):
        if f"n{h}" in D.columns: continue
        sell=g.close.shift(-h).where(~(D.di+h>lp),lc)
        D[f"n{h}"]=(sell/D.buy-1)*100-D.cost
    return D
K=prep("data/kp_hz2.pkl",10); Q=prep("data/kq_hz2.pkl",5)
gk=K.groupby("ticker",sort=False)
K["ret250"]=gk.close.transform(lambda x:x/x.shift(250)-1)*100
K["above20"]=gk.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
rng=np.random.default_rng(2026)
def dedup(X,h):
    keep=[];last={}
    for r in X.sort_values("di").itertuples():
        if r.ticker in last and r.di-last[r.ticker]<h: continue
        last[r.ticker]=r.di; keep.append(r.Index)
    return X.loc[keep]
def row(D,lab,M,h,base=None):
    X=D[(M&D.ok).fillna(False)]
    Y=dedup(X,h).dropna(subset=[f"n{h}"]).copy()
    if len(Y)<60: return None
    Y["ym"]=Y.date.str[:6]
    a=Y[Y.y<=2022][f"n{h}"].values; b=Y[Y.y>=2023]
    r=b[f"n{h}"].values
    if len(a)<25 or len(r)<25: return None
    pf=r[r>0].sum()/abs(r[r<=0].sum()) if (r<=0).any() else 99
    mo=[list(x.dropna()) for _,x in b.groupby("ym")[f"n{h}"]]; mo=[x for x in mo if x]
    bs=np.array([np.mean([v for i in rng.integers(0,len(mo),len(mo)) for v in mo[i]]) for _ in range(800)])
    lo,hi=np.percentile(bs,2.5),np.percentile(bs,97.5)
    mk="**" if lo>0 else ""
    keep=f" ({len(Y)/len(dedup(D[(base&D.ok).fillna(False)],h))*100:.0f}%)" if base is not None else ""
    print(f"| {lab} | {len(Y):,}{keep} | {a.mean():+.2f}% | {(r>0).mean()*100:.0f}% | **{r.mean():+.2f}%** | {np.median(r):+.2f}% | {pf:.2f} | {mk}{lo:+.1f}~{hi:+.1f}%{mk} |")
    return True
print("="*16+" A. 우리 규칙 + 원웨이 재료 "+"="*16)
RULES={
 "P3":(K,((K.ret20<=-20)&(K.su1>=2)&(K.fw60>=1)&(K.amt20>=3)&(~K.k60)&(K.srd==True)&(~K.dil)&K.u.notna()&(K.u<=-10)).fillna(False),20),
 "P4":(K,((K.u<=-20)&(K.dma20<=-10)&(K.srd==True)&K.ok).fillna(False),5),
 "D1":(Q,((Q.ret20<=-20)&(Q.su1>=2)&(Q.fw60>=1)&(Q.amt20>=2)&(~Q.k60)&(Q.srd==True)&(~Q.dil)&(Q.close>=1000)
        &(Q.ow20>=0)&Q.u.notna()&(Q.u<=-20)&(Q.부채비율.fillna(0)<=200)).fillna(False),20),
 "D2":(Q,(((Q.close>=1000)&(~Q.dil)&(Q.amt20>=5)&(Q.PBR<=0.5)&(Q.srd==True)&(Q.ret20<=-10)
        &(Q.u<=-10)&(Q.su1>=2)&(~Q.k60)&(Q.ow20>=0))).fillna(False),40)}
for k,(D,M,h) in RULES.items():
    print(f"\n### {k} + 원웨이 재료 ({h}일)\n")
    print("| 추가 조건 | 실거래 | 학습 | 검증승률 | **검증평균** | 중앙값 | PF | 월단위 95% |\n|---|---|---|---|---|---|---|---|")
    row(D,"없음(현행)",M,h)
    row(D,"5일선 위(반등 확인)",M&(D.dma5>0),h,M)
    row(D,"5일선 아래(더 눌림)",M&(D.dma5<=0),h,M)
    row(D,"60일 저점 +10% 이내",M&(D.fromlo60<=10),h,M)
    row(D,"60일 저점 +20% 초과(이미 반등)",M&(D.fromlo60>20),h,M)
    row(D,"고점 대비 -50% 이하(깊은 낙폭)",M&(D.fromhi60<=-50),h,M)
    row(D,"60일 최대낙폭 -40% 이하",M&(D.mdd60<=-40),h,M)
    row(D,"20일선 위 비율 ≤ 30%(추세 완전 붕괴)",M&(D.above20r<=30),h,M)
print("\n"+"="*16+" B. 원웨이 + 우리 재료 "+"="*16)
for D,label,amt in ((K,"코스피",10),(Q,"코스닥",5)):
    OW=((D.ret60>=30)&(D.above20r>=60)&(D.dma20<=2)&(D.dma20>=-3)).fillna(False)
    for h in (5,20):
        print(f"\n### {label} 원웨이(20일선 터치) + 우리 재료 · {h}일\n")
        print("| 추가 조건 | 실거래 | 학습 | 검증승률 | **검증평균** | 중앙값 | PF | 월단위 95% |\n|---|---|---|---|---|---|---|---|")
        row(D,"없음",OW,h)
        row(D,"외국인 5일 순매수 ≥ 3%",OW&(D.fw5>=3),h,OW)
        row(D,"외국인 60일 ≥ 1%",OW&(D.fw60>=1),h,OW)
        row(D,"기관 20일 ≥ 0",OW&(D.ow20>=0),h,OW)
        row(D,"공매도 감소",OW&(D.srd==True),h,OW)
        row(D,"공매도 비중 ≤ 0.5%",OW&(D.sr20<=0.5),h,OW)
        row(D,"업종 60일 ≥ 0(업종도 강함)",OW&(D.u>=0),h,OW)
        row(D,"PBR ≤ 1",OW&(D.PBR<=1),h,OW)
        row(D,"부채비율 ≤ 100%",OW&(D.부채비율<=100),h,OW)
        row(D,"거래량 침체 r16 < 80",OW&(D.r16<80),h,OW)
        row(D,"수급 3종(외인5·기관20·공매도감소)",OW&(D.fw5>=3)&(D.ow20>=0)&(D.srd==True),h,OW)
