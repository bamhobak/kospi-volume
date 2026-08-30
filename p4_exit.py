# -*- coding: utf-8 -*-
"""P4 보유기간 재검토 2 — 경로 기반 청산규칙 실측
   고정보유 외에: 익절 / 트레일링 / 20일선 이탈 / 거래량 급증(분산) / 조건소멸
   매수 = 다음날 시가. 각 보유일의 고가·저가·종가를 실제로 따라간다.
"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/bull_feat.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
g=D.groupby("ticker",sort=False)
D["ret250"]=g.close.transform(lambda x:x/x.shift(250)-1)*100
D["above20"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
D["ma20"]=g.close.transform(lambda x:x.rolling(20).mean())
D["vavg20"]=g.volume.transform(lambda x:x.rolling(20).mean())
M=(((D.fromhi>=-10)&(D.r16<120)&(D.rw1<=120)&(D.fw5>=3)&(D.fw60>=1)&(D.vol20<=3)
   &(D.sr20<=1)&(D.ret20<=10)&(D.amt20>=50)&(~D.dil)).fillna(False)
   & ~((D.above20>70)&(D.ret250>120)).fillna(False))
H=60
idx=np.where(M.values)[0]
tick=D.ticker.values; C=D.close.values; HI=D.high.values; LO=D.low.values
MA=D.ma20.values; VOL=D.volume.values; VA=D.vavg20.values
BUY=D.buy.values; COST=D.cost.values; Y=D.y.values; K60=D.k60.values; DT=D.date.values
paths=[]
for i in idx:
    b=BUY[i]
    if not np.isfinite(b): continue
    j=i+1; t=tick[i]; p=[]
    while j<len(D) and tick[j]==t and len(p)<H:
        p.append((C[j],HI[j],LO[j],MA[j],VOL[j],VA[j])); j+=1
    if len(p)<5: continue
    paths.append((i,b,COST[i],np.array(p,dtype=float)))
print(f"경로 확보 {len(paths):,}건 (평균 {np.mean([len(p[3]) for p in paths]):.0f}일)\n")

def run(rule):
    out=[]
    for i,b,cst,p in paths:
        r,d=rule(b,p)
        out.append((i,r-cst,d))
    return pd.DataFrame(out,columns=["i","r","d"]).assign(y=lambda x:Y[x.i],k60=lambda x:K60[x.i])
def fixed(n):
    def f(b,p):
        k=min(n,len(p))-1; return (p[k,0]/b-1)*100, k+1
    return f
def target(tg,cap):
    def f(b,p):
        for k in range(min(cap,len(p))):
            if p[k,1]>=b*(1+tg/100): return tg, k+1
        k=min(cap,len(p))-1; return (p[k,0]/b-1)*100, k+1
    return f
def trail(tr,cap):
    def f(b,p):
        pk=b
        for k in range(min(cap,len(p))):
            pk=max(pk,p[k,1])
            if p[k,2]<=pk*(1-tr/100): return max((pk*(1-tr/100))/b-1,-0.5)*100, k+1
        k=min(cap,len(p))-1; return (p[k,0]/b-1)*100, k+1
    return f
def ma_break(cap,grace=3):
    def f(b,p):
        for k in range(min(cap,len(p))):
            if k>=grace and np.isfinite(p[k,3]) and p[k,0]<p[k,3]: return (p[k,0]/b-1)*100, k+1
        k=min(cap,len(p))-1; return (p[k,0]/b-1)*100, k+1
    return f
def vol_spike(mult,cap):
    def f(b,p):
        for k in range(min(cap,len(p))):
            if np.isfinite(p[k,5]) and p[k,5]>0 and p[k,4]>=mult*p[k,5] and p[k,0]>b: return (p[k,0]/b-1)*100, k+1
        k=min(cap,len(p))-1; return (p[k,0]/b-1)*100, k+1
    return f
RULES=[("고정 10일",fixed(10)),("고정 15일",fixed(15)),("고정 20일",fixed(20)),("고정 30일",fixed(30)),("고정 40일",fixed(40)),
       ("익절+8%/40일",target(8,40)),("익절+10%/40일",target(10,40)),("익절+15%/40일",target(15,40)),
       ("익절+10%/20일",target(10,20)),("익절+8%/20일",target(8,20)),
       ("트레일-5%/40일",trail(5,40)),("트레일-8%/40일",trail(8,40)),("트레일-10%/40일",trail(10,40)),
       ("트레일-8%/20일",trail(8,20)),
       ("20일선 이탈/40일",ma_break(40)),("20일선 이탈/20일",ma_break(20)),
       ("거래량3배 분산/40일",vol_spike(3,40)),("거래량5배 분산/40일",vol_spike(5,40))]
print("## 청산규칙 비교 — 검증기간(2023~26)\n")
print("| 청산규칙 | 평균보유 | 학습 | **검증** | 중앙값 | 승률 | PF | 최악 | **검증 일당수익** |")
print("|---|---|---|---|---|---|---|---|---|")
res={}
for nm,fn in RULES:
    t=run(fn); res[nm]=t
    a=t[t.y<=2022]; b=t[t.y>=2023]
    r=b.r.values; pf=r[r>0].sum()/abs(r[r<=0].sum()) if (r<=0).any() else 99
    print(f"| {nm} | {b.d.mean():.0f}일 | {a.r.mean():+.2f}% | **{b.r.mean():+.2f}%** | {np.median(r):+.2f}% | "
          f"{(r>0).mean()*100:.0f}% | {pf:.2f} | {r.min():.0f}% | **{b.r.mean()/b.d.mean():+.3f}%** |")
import pickle; pickle.dump({k:v for k,v in res.items()},open("data/p4_exits.pkl","wb"))
