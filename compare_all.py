# -*- coding: utf-8 -*-
"""원래 규칙 vs 강화판 정면 비교 — 건당 / 총액 / 실제 계좌 / 표본 신뢰도"""
import io,sys,csv,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
IND={}
for r in csv.DictReader(open("data/industry.csv",encoding="utf-8-sig")):
    k=list(r.values()); IND[k[0]]=k[-1]
def addu(D):
    D=D.copy(); D["up"]=D.ticker.map(IND)
    d=D[D.up.notna()].dropna(subset=["ret60"]); g=d.groupby(["date","up"]).ret60
    med=g.median(); cnt=g.size(); med=med[cnt>=5]
    D["u"]=pd.MultiIndex.from_arrays([D.date,D.up]).map(med)
    return D
K=addu(pd.read_pickle("data/bull_feat.pkl")); Q=addu(pd.read_pickle("data/kd_feat.pkl"))
g=K.groupby("ticker",sort=False)
K["ret250"]=g.close.transform(lambda x:x/x.shift(250)-1)*100
K["above20"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
P1B=((K.fromhi>=-10)&(K.r16<120)&(K.rw1<=120)&(K.fw5>=3)&(K.fw60>=1)&(~K.dil)).fillna(False) \
    & ~((K.above20>70)&(K.ret250>120)).fillna(False)
RULES={
 "원래":{
  "P1":(K,(P1B&(K.vol20<=3)&(K.sr20<=1)&(K.ret20<=10)&(K.amt20>=50)).fillna(False),40),
  "P2":(K,((K.r16<30)&(K.rw1>=200)&(K.fw5>=2)&(K.amt>=3)&(K.ret3<=-5)&(K.ret10<=0)&(~K.k20)&(K.srd==True)&(~K.dil)).fillna(False),10),
  "P3":(K,((K.ret20<=-20)&(K.su1>=2)&(K.fw60>=1)&(K.amt20>=3)&(~K.k60)&(K.srd==True)&(~K.dil)&(K.u.isna()|(K.u<=-10))).fillna(False),20),
  "D1":(Q,((Q.ret20<=-20)&(Q.su1>=2)&(Q.fw60>=1)&(Q.amt20>=2)&(~Q.k60)&(Q.srd==True)&(~Q.dil)&(Q.close>=1000)&(Q.u.isna()|(Q.u<=-15))).fillna(False),20)},
 "강화":{
  "P1":(K,(P1B&(K.vol20<=2)&(K.sr20<=0.5)&(K.ret20<=5)&(K.amt20>=200)).fillna(False),40),
  "P2":(K,((K.r16<30)&(K.rw1>=200)&(K.fw5>=2)&(K.amt>=3)&(K.ret3<=-5)&(K.ret10<=0)&(~K.k20)&(K.srd==True)&(~K.dil)).fillna(False),10),
  "P3":(K,((K.ret20<=-20)&(K.su1>=2)&(K.fw60>=1)&(K.amt20>=3)&(~K.k60)&(K.srd==True)&(~K.dil)&K.u.notna()&(K.u<=-15)).fillna(False),20),
  "D1":(Q,((Q.ret20<=-20)&(Q.su1>=2)&(Q.fw60>=1)&(Q.amt20>=2)&(~Q.k60)&(Q.srd==True)&(~Q.dil)&(Q.close>=1000)&(Q.ow20>=0)&Q.u.notna()&(Q.u<=-25)).fillna(False),20)}}
CASH=3_000_000
print("## 1) 규칙별 — 원래 vs 강화 (검증기간 2023~26)\n")
print("| 규칙 | | 건수 | 건당 | 승률 | PF | 최악 | **검증 총손익(300만원씩)** |")
print("|---|---|---|---|---|---|---|---|")
TR={}
for ver in ("원래","강화"):
    TR[ver]=[]
    for nm,(D,m,h) in RULES[ver].items():
        s=D[m].copy(); s["R"]=nm; s["hold"]=h; s["r"]=s[f"n{h}"]
        TR[ver].append(s[["R","date","ticker","y","r","hold"]].dropna(subset=["r"]))
    TR[ver]=pd.concat(TR[ver],ignore_index=True)
for nm in ("P1","P2","P3","D1"):
    for ver in ("원래","강화"):
        v=TR[ver]; s=v[(v.R==nm)&(v.y>=2023)]
        if not len(s): continue
        r=s.r.values; pf=r[r>0].sum()/abs(r[r<=0].sum()) if (r<=0).any() else 99
        tot=len(v[v.R==nm])
        print(f"| {nm} | {ver} | {len(s)} (전체 {tot}) | **{r.mean():+.2f}%** | {(r>0).mean()*100:.0f}% | {pf:.2f} | {r.min():.0f}% | **{r.sum()/100*CASH/1e4:+,.0f}만원** |")
print("\n## 2) 네 규칙 합계 (검증기간)\n")
print("| | 거래수 | 건당 | 승률 | **총손익** | 필요자금(최대 동시보유) |\n|---|---|---|---|---|---|")
for ver in ("원래","강화"):
    v=TR[ver]; s=v[v.y>=2023]
    dates=sorted(v.date.unique()); DI={d:i for i,d in enumerate(dates)}
    cnt=np.zeros(len(dates)+60)
    for r in s.itertuples(): cnt[DI[r.date]:DI[r.date]+int(r.hold)]+=1
    print(f"| {ver} | {len(s):,} | {s.r.mean():+.2f}% | {(s.r>0).mean()*100:.0f}% | **{s.r.sum()/100*CASH/1e4:+,.0f}만원** | {int(cnt.max())}종목 = {int(cnt.max())*CASH/1e8:.1f}억 |")
import pickle; pickle.dump(TR,open("data/cmp_trades.pkl","wb"))
