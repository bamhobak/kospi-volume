# -*- coding: utf-8 -*-
"""신규 규칙이 기존 규칙과 '같은 시기'에 터지는가 — 자금 경쟁·분산 착시 검사"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
K=pd.read_pickle("data/kp_hz2.pkl"); Q=pd.read_pickle("data/kq_hz.pkl")
g=K.groupby("ticker",sort=False)
K["ret250"]=g.close.transform(lambda x:x/x.shift(250)-1)*100
K["above20"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
R={}
R["P1"]=(K,((K.fromhi>=-10)&(K.r16<120)&(K.rw1<=120)&(K.fw5>=3)&(K.fw60>=1)&(K.vol20<=2)&(K.sr20<=0.5)
        &(K.ret20<=5)&(K.amt20>=200)&(~K.dil)).fillna(False)&~((K.above20>70)&(K.ret250>120)).fillna(False),40)
R["P2"]=(K,((K.r16<30)&(K.rw1>=200)&(K.fw5>=2)&(K.amt>=3)&(K.ret3<=-5)&(K.ret10<=0)&(~K.k20)&(K.srd==True)&(~K.dil)).fillna(False),10)
R["P3"]=(K,((K.ret20<=-20)&(K.su1>=2)&(K.fw60>=1)&(K.amt20>=3)&(~K.k60)&(K.srd==True)&(~K.dil)&K.u.notna()&(K.u<=-10)).fillna(False),20)
R["D1"]=(Q,((Q.ret20<=-20)&(Q.su1>=2)&(Q.fw60>=1)&(Q.amt20>=2)&(~Q.k60)&(Q.srd==True)&(~Q.dil)&(Q.close>=1000)
        &(Q.ow20>=0)&Q.u.notna()&(Q.u<=-20)&(Q.부채비율.fillna(0)<=200)).fillna(False),20)
R["D2"]=(Q,(((Q.close>=1000)&(~Q.dil)&(Q.amt20>=5)&(Q.PBR<=0.5)&(Q.srd==True)&(Q.ret20<=-10)
        &(Q.u<=-10)&(Q.su1>=2)&(~Q.k60)&(Q.ow20>=0))).fillna(False),40)
R["NEW"]=(K,((K.u<=-20)&(K.dma20<=-10)&(K.srd==True)&K.ok).fillna(False),5)
T={k:v[0][v[1]] for k,v in R.items()}
HOLD={k:v[2] for k,v in R.items()}
alld=sorted(set(K.date)|set(Q.date)); DI={d:i for i,d in enumerate(alld)}
print("## 1) 신호가 난 '날'이 겹치는가 (검증기간 2023~26)\n")
DS={k:set(v[v.y>=2023].date) for k,v in T.items()}
print("| | "+" | ".join(DS)+" |\n|---|"+"---|"*len(DS))
for a in DS:
    row=[]
    for b in DS:
        if a==b: row.append(f"{len(DS[a])}일")
        else: row.append(f"{len(DS[a]&DS[b])/max(len(DS[a]),1)*100:.0f}%")
    print(f"| **{a}** | "+" | ".join(row)+" |")
print("\n(가로줄 = 그 규칙 신호일 중 세로 규칙도 신호가 난 비율)\n")
print("## 2) 보유 기간이 겹치는가 — 실제로 자금을 동시에 묶는 날\n")
occ={}
for k,v in T.items():
    a=np.zeros(len(alld),bool)
    for d in set(v[v.y>=2023].date):
        i=DI[d]; a[i:min(i+HOLD[k],len(alld))]=True
    occ[k]=a
tot=sum(1 for d in alld if d>="20230101")
print("| 규칙 | 보유 중인 날 | NEW 와 동시 | NEW 보유일 중 비율 |\n|---|---|---|---|")
nd=occ["NEW"].sum()
for k in ("P1","P2","P3","D1","D2"):
    both=(occ[k]&occ["NEW"]).sum()
    print(f"| {k} | {occ[k].sum()}일 | {both}일 | **{both/max(nd,1)*100:.0f}%** |")
print(f"\nNEW 보유일 {nd}일 / 검증 전체 {tot}일 ({nd/tot*100:.0f}%)")
anyo=np.zeros(len(alld),bool)
for k in ("P1","P2","P3","D1","D2"): anyo|=occ[k]
print(f"NEW 보유 중 **다른 규칙도 하나 이상 보유한 날: {(anyo&occ['NEW']).sum()}일 ({(anyo&occ['NEW']).sum()/max(nd,1)*100:.0f}%)**")
print("\n## 3) 월별 수익 상관 (같이 오르내리는가)\n")
mon={}
for k,v in T.items():
    x=v[v.y>=2023].copy(); x["ym"]=x.date.str[:6]
    mon[k]=x.groupby("ym")[f"n{HOLD[k]}"].mean()
M=pd.DataFrame(mon)
print("| | "+" | ".join(M.columns)+" |\n|---|"+"---|"*len(M.columns))
C=M.corr()
for a in M.columns:
    print(f"| **{a}** | "+" | ".join(f"{C.loc[a,b]:+.2f}" if not np.isnan(C.loc[a,b]) else "-" for b in M.columns)+" |")
print(f"\n공통 관측 월수: NEW vs P3 {M[['NEW','P3']].dropna().shape[0]}개월 · NEW vs D1 {M[['NEW','D1']].dropna().shape[0]}개월")
print("\n## 4) 시장 국면 분포\n")
print("| 규칙 | 코스피 60일선 위 | 아래 |\n|---|---|---|")
for k,v in T.items():
    x=v[v.y>=2023]
    if "k60" not in x: continue
    print(f"| {k} | {x.k60.mean()*100:.0f}% | {(~x.k60).mean()*100:.0f}% |")
