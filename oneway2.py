# -*- coding: utf-8 -*-
"""원웨이 재실측 — 기준가 정의 7종 × 청산 5종
   기준가(진입): 5·10·20일선 터치 / 전고점 되돌림 -5·-10·-15% / 20일 VWAP
   청산: 5일선 이탈 · 20일선 이탈 · 트레일 -8% · 트레일 -15% · 고정 20일
"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
def prep(path,amtmin):
    D=pd.read_pickle(path).sort_values(["ticker","date"]).reset_index(drop=True)
    g=D.groupby("ticker",sort=False)
    for w in (5,10):
        D[f"ma{w}"]=g.close.transform(lambda x,w=w: x.rolling(w).mean())
        D[f"dma{w}"]=(D.close/D[f"ma{w}"]-1)*100
    D["ma20v"]=g.close.transform(lambda x:x.rolling(20).mean())
    pv=(D.close*D.volume.astype(float))
    D["vwap20"]=pv.groupby(D.ticker).transform(lambda x:x.rolling(20).sum())/g.volume.transform(lambda x:x.rolling(20).sum()).replace(0,np.nan)
    D["dvwap"]=(D.close/D.vwap20-1)*100
    D["hi60"]=g.close.transform(lambda x:x.rolling(60,min_periods=30).max())
    D["fromhi60"]=(D.close/D.hi60-1)*100
    D["dd"]=(D.close/D.hi60-1)*100
    D["mdd60"]=g["dd"].transform(lambda x:x.rolling(60,min_periods=30).min())
    D["above20r"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(60,min_periods=30).mean())*100
    D["ok"]=((D.close>=1000)&(~D.dil)&(D.amt20>=amtmin)).fillna(False)
    return D
K=prep("data/kp_hz2.pkl",10); Q=prep("data/kq_hz2.pkl",5)
print(f"코스피 {len(K):,}행 · 코스닥 {len(Q):,}행\n")
MAXH=60
def build_paths(D,M):
    idx=np.where((M&D.ok).fillna(False).values)[0]
    tick=D.ticker.values; C=D.close.values; LO=D.low.values; HI=D.high.values
    MA5=D.ma5.values; MA20=D.ma20v.values; BUY=D.buy.values; COST=D.cost.values
    Y=D.y.values; DT=D.date.values; TK=D.ticker.values
    out=[]
    for i in idx:
        b=BUY[i]
        if not np.isfinite(b): continue
        j=i+1; t=tick[i]; p=[]
        while j<len(D) and tick[j]==t and len(p)<MAXH:
            p.append((C[j],LO[j],HI[j],MA5[j],MA20[j])); j+=1
        if len(p)<3: continue
        out.append((DT[i],TK[i],Y[i],b,COST[i],np.array(p,dtype=float)))
    return out
def exits(paths,kind,**o):
    res=[]
    for dt,tk,y,b,cst,p in paths:
        n=len(p); r=None
        if kind=="fixed":
            k=min(o["n"],n)-1; r=((p[k,0]/b-1)*100,k+1)
        elif kind in ("ma5","ma20"):
            col=3 if kind=="ma5" else 4
            for k in range(n):
                if k>=o.get("grace",2) and np.isfinite(p[k,col]) and p[k,0]<p[k,col]:
                    r=((p[k,0]/b-1)*100,k+1); break
        elif kind=="trail":
            pk=b
            for k in range(n):
                pk=max(pk,p[k,2])
                if p[k,1]<=pk*(1-o["t"]/100):
                    r=(max(pk*(1-o["t"]/100)/b-1,-0.6)*100,k+1); break
        if r is None: r=((p[n-1,0]/b-1)*100,n)
        res.append((dt,tk,y,r[0]-cst,r[1]))
    return pd.DataFrame(res,columns=["date","ticker","y","r","d"])
rng=np.random.default_rng(99)
def dedup(T,D):
    dates=sorted(D.date.unique()); DI={d:i for i,d in enumerate(dates)}
    T=T.copy(); T["di"]=T.date.map(DI)
    keep=[];last={}
    for r in T.sort_values("di").itertuples():
        if r.ticker in last and r.di-last[r.ticker]<r.d: continue
        last[r.ticker]=r.di+int(r.d); keep.append(r.Index)
    return T.loc[keep]
def show(D,label,entry_name,M):
    paths=build_paths(D,M)
    if len(paths)<200: print(f"\n### {label} · {entry_name} — 표본 {len(paths)}건 부족\n"); return
    print(f"\n### {label} · {entry_name}  (신호 {len(paths):,}건)\n")
    print("| 청산 | 실거래 | 평균보유 | 학습평균 | **검증승률** | **검증평균** | 중앙값 | PF | 월단위 95% |")
    print("|---|---|---|---|---|---|---|---|---|")
    for nm,kind,o in [("5일선 이탈","ma5",{}),("20일선 이탈","ma20",{}),
                      ("트레일 -8%","trail",{"t":8}),("트레일 -15%","trail",{"t":15}),
                      ("고정 20일","fixed",{"n":20})]:
        T=exits(paths,kind,**o)
        Y=dedup(T,D); Y["ym"]=Y.date.str[:6]
        a=Y[Y.y<=2022].r.values; b=Y[Y.y>=2023]
        r=b.r.values
        if len(a)<50 or len(r)<40: continue
        pf=r[r>0].sum()/abs(r[r<=0].sum()) if (r<=0).any() else 99
        mo=[list(x) for _,x in b.groupby("ym").r]; mo=[x for x in mo if x]
        bs=np.array([np.mean([v for i in rng.integers(0,len(mo),len(mo)) for v in mo[i]]) for _ in range(800)])
        lo,hi=np.percentile(bs,2.5),np.percentile(bs,97.5)
        mk="**" if lo>0 else ""
        print(f"| {nm} | {len(Y):,} | {b.d.mean():.0f}일 | {a.mean():+.2f}% | {(r>0).mean()*100:.0f}% | **{r.mean():+.2f}%** | {np.median(r):+.2f}% | {pf:.2f} | {mk}{lo:+.1f}~{hi:+.1f}%{mk} |")
for D,label in ((K,"코스피"),(Q,"코스닥")):
    OW=((D.ret60>=30)&(D.above20r>=60)).fillna(False)
    show(D,label,"기준가 = 5일선 터치 (이격 -2~+1%)",  OW&(D.dma5<=1)&(D.dma5>=-2))
    show(D,label,"기준가 = 10일선 터치 (-2~+1%)",      OW&(D.dma10<=1)&(D.dma10>=-2))
    show(D,label,"기준가 = 20일선 터치 (-3~+2%)",      OW&(D.dma20<=2)&(D.dma20>=-3))
    show(D,label,"기준가 = 60일 고점 대비 -10% 되돌림", OW&(D.fromhi60<=-8)&(D.fromhi60>=-13))
    show(D,label,"기준가 = 20일 VWAP 근처 (-3~+2%)",   OW&(D.dvwap<=2)&(D.dvwap>=-3))
