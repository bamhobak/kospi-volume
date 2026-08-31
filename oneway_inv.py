# -*- coding: utf-8 -*-
"""원웨이 역발상 두 가지
   A. 공매도 — 원웨이 눌림 조건에서 '판다'(수익률 부호 반전, 비용 재차감)
   B. 역조건 매수 — 강한 하락추세(60일 -30%)에서 같은 기준가(이평선) 도달 시 매수
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
    D["dd"]=(D.close/D.hi60-1)*100
    D["mdd60"]=g["dd"].transform(lambda x:x.rolling(60,min_periods=30).min())
    D["above20r"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(60,min_periods=30).mean())*100
    D["fromlo60"]=(D.close/D.lo60-1)*100
    D["ok"]=((D.close>=1000)&(~D.dil)&(D.amt20>=amtmin)).fillna(False)
    dates=sorted(D.date.unique()); DI={x:i for i,x in enumerate(dates)}
    lp=g.date.transform("max").map(DI); lc=g.close.transform("last"); mp=D.date.map(DI)
    for h in (3,5,10,20,40):
        if f"n{h}" in D.columns: continue
        sell=g.close.shift(-h).where(~(mp+h>lp),lc)
        D[f"n{h}"]=(sell/D.buy-1)*100-D.cost
    # 공매도 수익 = -(가격변화) - 비용 (대차수수료 연3% 근사 포함)
    for h in (3,5,10,20,40):
        gross=(D[f"n{h}"]+D.cost)          # 비용 빼기 전 가격변화
        D[f"s{h}"]=-gross-D.cost-3.0*h/246
    D["di"]=D.date.map(DI)
    return D
K=prep("data/kp_hz2.pkl",10); Q=prep("data/kq_hz2.pkl",5)
rng=np.random.default_rng(123)
def dedup(X,h):
    keep=[];last={}
    for r in X.sort_values("di").itertuples():
        if r.ticker in last and r.di-last[r.ticker]<h: continue
        last[r.ticker]=r.di; keep.append(r.Index)
    return X.loc[keep]
def ev(D,label,name,M,col):
    X=D[(M&D.ok).fillna(False)]
    if len(X)<300: print(f"\n### {label} · {name} — 표본 {len(X)}건 부족\n"); return
    print(f"\n### {label} · {name}  (신호 {len(X):,}건 · 고유 종목 {X.ticker.nunique():,})\n")
    print("| 보유 | 실거래 | 학습승률 | 학습평균 | **검증승률** | **검증평균** | 중앙값 | PF | 최악 | 월단위 95% |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for h in (3,5,10,20,40):
        Y=dedup(X,h).dropna(subset=[f"{col}{h}"]).copy(); Y["ym"]=Y.date.str[:6]
        a=Y[Y.y<=2022][f"{col}{h}"].values; b=Y[Y.y>=2023]
        r=b[f"{col}{h}"].values
        if len(a)<50 or len(r)<40: continue
        pf=r[r>0].sum()/abs(r[r<=0].sum()) if (r<=0).any() else 99
        mo=[list(x.dropna()) for _,x in b.groupby("ym")[f"{col}{h}"]]; mo=[x for x in mo if x]
        bs=np.array([np.mean([v for i in rng.integers(0,len(mo),len(mo)) for v in mo[i]]) for _ in range(800)])
        lo,hi=np.percentile(bs,2.5),np.percentile(bs,97.5)
        mk="**" if lo>0 else ""
        print(f"| {h}일 | {len(Y):,} | {(a>0).mean()*100:.0f}% | {a.mean():+.2f}% | {(r>0).mean()*100:.0f}% | **{r.mean():+.2f}%** | {np.median(r):+.2f}% | {pf:.2f} | {r.min():.0f}% | {mk}{lo:+.1f}~{hi:+.1f}%{mk} |")
print("="*20+" A. 공매도 (원웨이 눌림에서 판다) "+"="*20)
for D,label in ((K,"코스피"),(Q,"코스닥")):
    OW=((D.ret60>=30)&(D.above20r>=60)).fillna(False)
    ev(D,label,"원웨이 + 20일선 터치 → 공매도",OW&(D.dma20<=2)&(D.dma20>=-3),"s")
    ev(D,label,"원웨이 + 5일선 터치 → 공매도",OW&(D.dma5<=1)&(D.dma5>=-2),"s")
    ev(D,label,"원웨이 전체 → 공매도",OW,"s")
print("\n"+"="*20+" B. 역조건 매수 (강한 하락추세 + 기준가) "+"="*20)
for D,label in ((K,"코스피"),(Q,"코스닥")):
    DW=((D.ret60<=-30)&(D.above20r<=40)).fillna(False)
    ev(D,label,"하락추세 + 20일선 터치 → 매수",DW&(D.dma20<=2)&(D.dma20>=-3),"n")
    ev(D,label,"하락추세 + 5일선 터치 → 매수",DW&(D.dma5<=1)&(D.dma5>=-2),"n")
    ev(D,label,"하락추세 + 60일 저점 근처(+10% 이내) → 매수",DW&(D.fromlo60<=10),"n")
    ev(D,label,"하락추세 전체 → 매수",DW,"n")
