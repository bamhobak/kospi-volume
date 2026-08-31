# -*- coding: utf-8 -*-
"""원웨이 패턴 실측 — 일자형(조정 없음) vs 계단식(얕은 조정 반복)
   영상 요지를 측정 가능한 조건으로 옮긴다:
     · 원웨이 = 강한 상승추세 (60일 큰 상승 + 20일선·60일선 위 + 되돌림 적음)
     · 일자형 = 가격 조정 없이 시간 조정만 → 60일 최대낙폭이 아주 작음
     · 계단식 = 얕은 조정을 반복 → 60일 최대낙폭이 중간
   진입 시점: 일자형 = 아주 짧은 조정 직후 / 계단식 = 기준가(20일선) 도달
"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
HZ=[3,5,10,20,40]
def prep(path,amtmin,out):
    D=pd.read_pickle(path).sort_values(["ticker","date"]).reset_index(drop=True)
    g=D.groupby("ticker",sort=False)
    for h in HZ:
        if f"n{h}" in D.columns: continue
        dates=sorted(D.date.unique()); DI={x:i for i,x in enumerate(dates)}
        lp=g.date.transform("max").map(DI); lc=g.close.transform("last"); mp=D.date.map(DI)
        sell=g.close.shift(-h).where(~(mp+h>lp),lc)
        D[f"n{h}"]=(sell/D.buy-1)*100-D.cost
    # 추세·조정 지표
    D["ma5"]=g.close.transform(lambda x:x.rolling(5).mean())
    D["dma5"]=(D.close/D.ma5-1)*100
    D["hi60"]=g.close.transform(lambda x:x.rolling(60,min_periods=30).max())
    # 60일 최대 낙폭: 그 구간 각 시점의 고점 대비 최저 되돌림
    D["dd"]=(D.close/g.close.transform(lambda x:x.rolling(60,min_periods=30).max())-1)*100
    D["mdd60"]=g["dd"].transform(lambda x:x.rolling(60,min_periods=30).min())
    D["above20r"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(60,min_periods=30).mean())*100
    D["ok"]=((D.close>=1000)&(~D.dil)&(D.amt20>=amtmin)).fillna(False)
    D.to_pickle(out); return D
K=prep("data/kp_hz2.pkl",10,"data/kp_ow.pkl")
Q=prep("data/kq_hz2.pkl",5,"data/kq_ow.pkl")
print(f"코스피 {len(K):,}행 · 코스닥 {len(Q):,}행\n")
def dedup(X,h,D):
    dates=sorted(D.date.unique()); DI={d:i for i,d in enumerate(dates)}
    X=X.copy(); X["di"]=X.date.map(DI)
    keep=[];last={}
    for r in X.sort_values("di").itertuples():
        if r.ticker in last and r.di-last[r.ticker]<h: continue
        last[r.ticker]=r.di; keep.append(r.Index)
    return X.loc[keep]
rng=np.random.default_rng(77)
def ev(D,label,name,M,hs=HZ):
    X=D[(M&D.ok).fillna(False)]
    if len(X)<100: print(f"\n### {label} · {name} — 표본 {len(X)}건, 부족\n"); return
    print(f"\n### {label} · {name}\n")
    print(f"원본 {len(X):,}건 · 고유 종목 {X.ticker.nunique():,} · 고유 날짜 {X.date.nunique():,}\n")
    print("| 보유 | 실거래 | 학습승률 | 학습평균 | **검증승률** | **검증평균** | 중앙값 | PF | 월단위 95% |")
    print("|---|---|---|---|---|---|---|---|---|")
    for h in hs:
        Y=dedup(X,h,D); Y=Y.dropna(subset=[f"n{h}"]).copy(); Y["ym"]=Y.date.str[:6]
        a=Y[Y.y<=2022][f"n{h}"].values; b=Y[Y.y>=2023]
        r=b[f"n{h}"].values
        if len(a)<50 or len(r)<40: continue
        pf=r[r>0].sum()/abs(r[r<=0].sum()) if (r<=0).any() else 99
        mo=[list(x.dropna()) for _,x in b.groupby("ym")[f"n{h}"]]; mo=[x for x in mo if x]
        bs=np.array([np.mean([v for i in rng.integers(0,len(mo),len(mo)) for v in mo[i]]) for _ in range(1000)])
        lo,hi=np.percentile(bs,2.5),np.percentile(bs,97.5)
        mk="**" if lo>0 else ""
        print(f"| {h}일 | {len(Y):,} | {(a>0).mean()*100:.0f}% | {a.mean():+.2f}% | {(r>0).mean()*100:.0f}% | **{r.mean():+.2f}%** | {np.median(r):+.2f}% | {pf:.2f} | {mk}{lo:+.1f}~{hi:+.1f}%{mk} |")
for D,label,amt in ((K,"코스피",10),(Q,"코스닥",5)):
    # 기준선: 강한 상승추세 종목 전체
    ONEWAY=(D.ret60>=30)&(D.close>D.ma20 if "ma20" in D else D.dma20>0)&(D.dma20>0)&(D.k60|True)
    ONEWAY=((D.ret60>=30)&(D.dma20>0)&(D.above20r>=60)).fillna(False)
    ev(D,label,"원웨이 전체(60일 +30%·20일선 위·추세 지속)",ONEWAY)
    ev(D,label,"일자형 — 조정 거의 없음(60일 최대낙폭 ≥ -10%)",ONEWAY&(D.mdd60>=-10))
    ev(D,label,"일자형 + 짧은 조정 직후(3일 수익 ≤ 0)",ONEWAY&(D.mdd60>=-10)&(D.ret3<=0))
    ev(D,label,"계단식 — 얕은 조정 반복(낙폭 -10~-25%)",ONEWAY&(D.mdd60<-10)&(D.mdd60>=-25))
    ev(D,label,"계단식 + 기준가(20일선) 도달(이격 -3~+2%)",ONEWAY&(D.mdd60<-10)&(D.mdd60>=-25)&(D.dma20<=2)&(D.dma20>=-3))
