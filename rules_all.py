# -*- coding: utf-8 -*-
"""네 규칙(P2·P3·P4 코스피 / D1 코스닥)의 거래 분포를 현재 사이트 정의대로 재산출.
   배분 비중 계산의 입력이 되므로 업종 조건까지 그대로 반영한다.
"""
import io,sys,csv,sqlite3,numpy as np,pandas as pd
from collections import defaultdict
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
IND={}
for r in csv.DictReader(open("data/industry.csv",encoding="utf-8-sig")):
    k=list(r.values()); IND[k[0]]=k[-1] if len(k)>1 else None
print(f"업종 매핑 {len(IND):,}종목")

def upjong60(df):
    """업종별 60거래일 수익률 (각 날짜 기준, 소속 종목 중앙값)"""
    d=df[["date","ticker","close"]].copy()
    d["up"]=d.ticker.map(IND)
    d=d[d.up.notna()]
    g=d.sort_values(["ticker","date"]).groupby("ticker",sort=False)
    d["r60"]=g.close.transform(lambda x:x/x.shift(60)-1)*100
    m=d.dropna(subset=["r60"]).groupby(["date","up"]).r60.median()
    return m

# ── 코스피 ────────────────────────────────────────────────────
K=pd.read_pickle("data/bull_feat.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
g=K.groupby("ticker",sort=False)
K["ret250"]=g.close.transform(lambda x:x/x.shift(250)-1)*100
K["above20"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
U=upjong60(K); K["up"]=K.ticker.map(IND)
K["sr60"]=pd.MultiIndex.from_arrays([K.date,K.up]).map(U)
print(f"코스피 업종60일 채움 {K.sr60.notna().mean()*100:.0f}%")
RULES={}
RULES["P2"]=dict(m=((K.r16<30)&(K.rw1>=200)&(K.fw5>=2)&(K.amt>=3)&(K.ret3<=-5)&(K.ret10<=0)
                    &(~K.k20)&(K.srd==True)&(~K.dil)&(~K.pref if "pref" in K else True)).fillna(False), col="n10", src=K)
RULES["P3"]=dict(m=((K.ret20<=-20)&(K.su1>=2)&(K.fw60>=1)&(K.amt20>=3)&(~K.k60)
                    &(K.sr60.isna()|(K.sr60<=-10))&(K.srd==True)&(~K.dil)).fillna(False), col="n20", src=K)
RULES["P4"]=dict(m=(((K.fromhi>=-10)&(K.r16<120)&(K.rw1<=120)&(K.fw5>=3)&(K.fw60>=1)&(K.vol20<=3)
                    &(K.sr20<=1)&(K.ret20<=10)&(K.amt20>=50)&(~K.dil)).fillna(False)
                    & ~((K.above20>70)&(K.ret250>120)).fillna(False)), col="n40", src=K)
dates=sorted(K.date.unique()); DI={d:i for i,d in enumerate(dates)}
lastpos=g.date.transform("max").map(DI); lastclose=g.close.transform("last"); mypos=K.date.map(DI)
for h in (10,20,40):
    if f"n{h}" not in K:
        sell=g.close.shift(-h).where(~(mypos+h>lastpos), lastclose)
        K[f"n{h}"]=(sell/K.buy-1)*100-K.cost
print()
for nm,v in RULES.items():
    t=v["src"][v["m"]]
    r=t[v["col"]].dropna()
    print(f"{nm}: {len(r):,}건 (검증 {len(t[t.y>=2023]):,}건)")
out=[]
for nm,v in RULES.items():
    t=v["src"][v["m"]].copy(); t["r"]=t[v["col"]]; t["R"]=nm; t["hold"]={"P2":10,"P3":20,"P4":40}[nm]
    out.append(t[["R","date","ticker","name","y","r","hold","k60"]].dropna(subset=["r"]))
pd.concat(out).to_csv("data/rules_trades_kospi.csv",index=False,encoding="utf-8-sig")
print("\n저장: data/rules_trades_kospi.csv")
