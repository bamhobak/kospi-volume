# -*- coding: utf-8 -*-
"""청산규칙 강건성 — 파라미터를 훑어 '한 칸만 좋은지' 확인 + 선행편향 제거판(익일 시가 청산)"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/bull_feat.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
g=D.groupby("ticker",sort=False)
D["ret250"]=g.close.transform(lambda x:x/x.shift(250)-1)*100
D["above20"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
D["vavg20"]=g.volume.transform(lambda x:x.rolling(20).mean())
M=(((D.fromhi>=-10)&(D.r16<120)&(D.rw1<=120)&(D.fw5>=3)&(D.fw60>=1)&(D.vol20<=3)
   &(D.sr20<=1)&(D.ret20<=10)&(D.amt20>=50)&(~D.dil)).fillna(False)
   & ~((D.above20>70)&(D.ret250>120)).fillna(False))
H=60; idx=np.where(M.values)[0]
tick=D.ticker.values; C=D.close.values; OP=D.open.values; VOL=D.volume.values; VA=D.vavg20.values
BUY=D.buy.values; COST=D.cost.values; Y=D.y.values; K60=D.k60.values
paths=[]
for i in idx:
    b=BUY[i]
    if not np.isfinite(b): continue
    j=i+1; t=tick[i]; p=[]
    while j<len(D) and tick[j]==t and len(p)<H:
        p.append((C[j],VOL[j],VA[j],OP[j+1] if (j+1<len(D) and tick[j+1]==t) else np.nan)); j+=1
    if len(p)<5: continue
    paths.append((i,b,COST[i],np.array(p,dtype=float)))
def run(mult,cap,nextopen=False,minprof=0.0):
    out=[]
    for i,b,cst,p in paths:
        n=min(cap,len(p)); r=None
        for k in range(n):
            if np.isfinite(p[k,2]) and p[k,2]>0 and p[k,1]>=mult*p[k,2] and (p[k,0]/b-1)*100>=minprof:
                px=p[k,3] if nextopen else p[k,0]
                if nextopen and not np.isfinite(px): px=p[k,0]
                r=((px/b-1)*100, k+1+(1 if nextopen else 0)); break
        if r is None: r=((p[n-1,0]/b-1)*100, n)
        out.append((i,r[0]-cst,r[1]))
    t=pd.DataFrame(out,columns=["i","r","d"]); t["y"]=Y[t.i]; return t
print("## 거래량 급증 청산 — 배수 × 상한 스윕 (선행편향 제거: 급증 다음날 시가 매도)\n")
print("| 배수 | 상한 | 평균보유 | 학습 | **검증** | 중앙값 | 승률 | PF | 일당수익 |\n|---|---|---|---|---|---|---|---|---|")
for mult in (2,2.5,3,4,5):
    for cap in (20,30,40):
        t=run(mult,cap,nextopen=True)
        a=t[t.y<=2022]; b=t[t.y>=2023]; r=b.r.values
        pf=r[r>0].sum()/abs(r[r<=0].sum()) if (r<=0).any() else 99
        print(f"| {mult}배 | {cap}일 | {b.d.mean():.0f}일 | {a.r.mean():+.2f}% | **{b.r.mean():+.2f}%** | {np.median(r):+.2f}% | {(r>0).mean()*100:.0f}% | {pf:.2f} | {b.r.mean()/b.d.mean():+.3f}% |")
print("\n## 당일 종가 매도 vs 익일 시가 매도 (선행편향 크기)\n")
print("| 배수/상한 | 당일종가 검증 | 익일시가 검증 | 차이 |\n|---|---|---|---|")
for mult,cap in ((2.5,40),(3,40),(3,30),(4,40)):
    x=run(mult,cap,False); z=run(mult,cap,True)
    xb=x[x.y>=2023].r.mean(); zb=z[z.y>=2023].r.mean()
    print(f"| {mult}배/{cap}일 | {xb:+.2f}% | {zb:+.2f}% | {zb-xb:+.2f}%p |")
