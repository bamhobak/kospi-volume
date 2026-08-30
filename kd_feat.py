# -*- coding: utf-8 -*-
"""코스닥 피처 행렬 — 새 규칙(D2) 탐색용. bull_feat.py 의 코스닥판.
   폐지 493종목 포함(생존편향 제거) · 코스닥은 비용 한 단계 위 · 주가 1,000원 하한은 규칙에서 처리.
"""
import io,sys,csv,sqlite3
from collections import defaultdict
import numpy as np, pandas as pd
import FinanceDataReader as fdr
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
c=sqlite3.connect("file:data/kosdaq.db?mode=ro",uri=True,timeout=900)
SUR=pd.read_sql("""SELECT date,ticker,name,open,high,low,close,volume,frgn,organ,foreign_ratio FROM daily
    WHERE close>0 AND open>0 AND date>='20170101' ORDER BY ticker,date""",c);c.close()
c=sqlite3.connect("file:data/delisted_kd.db?mode=ro",uri=True,timeout=900)
DEL=pd.read_sql("""SELECT date,ticker,name,open,high,low,close,volume,frgn,organ,foreign_ratio FROM daily
    WHERE close>0 AND open>0 AND date>='20170101' ORDER BY ticker,date""",c);c.close()
DEL=DEL[~DEL.ticker.isin(set(SUR.ticker))]
SUR["grp"],DEL["grp"]="생존","폐지"
df=pd.concat([SUR,DEL],ignore_index=True)
df=df[df.ticker.str.endswith("0")].sort_values(["ticker","date"]).reset_index(drop=True)
dates=sorted(df.date.unique()); DI={d:i for i,d in enumerate(dates)}
print(f"코스닥 보통주 {df.ticker.nunique():,}종목 {len(df):,}행 {dates[0]}~{dates[-1]} (폐지 {DEL.ticker.nunique()}종목)")
# 공매도
k=sqlite3.connect("file:data/kis/market.db?mode=ro",uri=True,timeout=300)
ss=pd.read_sql("SELECT date,ticker,short_ratio FROM short_sale WHERE short_ratio IS NOT NULL ORDER BY ticker,date",k);k.close()
ss=ss[ss.ticker.isin(set(df.ticker))]
gs=ss.groupby("ticker").short_ratio
ss["srd"]=gs.transform(lambda x:x.rolling(5).mean())<gs.transform(lambda x:x.rolling(20).mean())
ss["sr20"]=gs.transform(lambda x:x.rolling(20).mean())
df=df.merge(ss[["date","ticker","srd","sr20"]],on=["date","ticker"],how="left")
# 증자
d=sqlite3.connect("file:data/dart/disclosures.db?mode=ro",uri=True,timeout=300)
dz=pd.read_sql("""SELECT stock_code t, rcept_dt FROM disclosure WHERE
   replace(report_nm,' ','') LIKE '%유상증자결정%' OR replace(report_nm,' ','') LIKE '%전환사채권발행결정%'
   OR replace(report_nm,' ','') LIKE '%신주인수권부사채권발행결정%'""",d);d.close()
DIL=defaultdict(list)
for r in dz.itertuples(): DIL[r.t].append(r.rcept_dt)
# 지수 (코스피·코스닥 둘 다)
for nm,sym in (("k","KS11"),("q","KQ11")):
    ix=fdr.DataReader(sym,"2015-06-01"); ix=ix[ix.Close>0]; ix.index=ix.index.strftime("%Y%m%d")
    cl=ix["Close"].reindex(dates).ffill()
    for w in (20,60):
        df[f"{nm}{w}"]=df.date.map(cl>cl.rolling(w).mean()).fillna(False).values
g=df.groupby("ticker",sort=False)
V,C=df.volume.astype(float),df.close
df["a40"]=g["volume"].transform(lambda x:x.shift(3).rolling(40).mean())
df["a240"]=g["volume"].transform(lambda x:x.shift(43).rolling(240).mean())
df["r16"]=df.a40/df.a240*100
df["rw1"]=g["volume"].transform(lambda x:x.rolling(3).mean())/df.a40*100
df["su1"]=V/g["volume"].transform(lambda x:x.shift(1).rolling(20).mean())
amt=V*C
df["amt20"]=amt.groupby(df.ticker).transform(lambda x:x.rolling(20).mean())/1e8
df["amt"]=amt.groupby(df.ticker).transform(lambda x:x.rolling(40).mean()).shift(3)/1e8
for w in (5,20,60):
    vs=g["volume"].transform(lambda x,w=w:x.rolling(w).sum()).replace(0,np.nan)
    df[f"fw{w}"]=g["frgn"].transform(lambda x,w=w:x.fillna(0).rolling(w).sum())/vs*100
    df[f"ow{w}"]=g["organ"].transform(lambda x,w=w:x.fillna(0).rolling(w).sum())/vs*100
for n in (3,5,10,20,60,120,250):
    df[f"ret{n}"]=g.close.transform(lambda x,n=n:x/x.shift(n)-1)*100
df["ret500"]=g.close.transform(lambda x:x/x.shift(500)-1)*100
for w in (20,60):
    df[f"dma{w}"]=(C/g.close.transform(lambda x,w=w:x.rolling(w).mean())-1)*100
df["hi250"]=g.close.transform(lambda x:x.rolling(250,min_periods=60).max())
df["lo250"]=g.close.transform(lambda x:x.rolling(250,min_periods=60).min())
df["fromhi"]=(C/df.hi250-1)*100; df["fromlo"]=(C/df.lo250-1)*100
df["vol20"]=g.close.transform(lambda x:(x/x.shift(1)-1).rolling(20).std())*100
df["above20"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
df["clv"]=np.where(df.high>df.low,(C-df.low)/(df.high-df.low),0.5)
df["y"]=df.date.str[:4].astype(int)
ds=pd.to_datetime(df.date); dil=np.zeros(len(df),bool)
for t,idx in df.groupby("ticker").indices.items():
    L=pd.to_datetime(DIL.get(t,[]))
    if len(L)==0: continue
    for i,x in zip(idx,ds.values[idx]):
        dil[i]=bool(((L.values>=x-np.timedelta64(90,"D"))&(L.values<=x)).any())
df["dil"]=dil
df["cost"]=0.18+np.select([df.amt20>=100,df.amt20>=50,df.amt20>=20,df.amt20>=10],[.30,.50,.70,1.00],default=1.30)
pc=g.close.shift(1); jj=(C/pc).where(pc>0)
badday=((jj>1.32)|(jj<0.68)).fillna(False)
bad=np.zeros(len(df),bool); pos=df.date.map(DI).values
for t,sub in df[badday].groupby("ticker"):
    idx=df.index[df.ticker==t].values
    bp=np.sort([DI[x] for x in sub.date if x in DI]); p=pos[idx]
    q=np.searchsorted(bp,p,side="right")
    bad[idx[(q<len(bp))&(bp[np.minimum(q,len(bp)-1)]-p<=42)]]=True
print(f"불연속 인접 {int(bad.sum()):,}행")
df["buy"]=g.open.shift(-1)
lastpos=g.date.transform("max").map(DI); lastclose=g.close.transform("last"); mypos=df.date.map(DI)
for h in (10,20,40):
    sell=g.close.shift(-h).where(~(mypos+h>lastpos),lastclose)
    df[f"n{h}"]=(sell/df.buy-1)*100-df.cost
D=df[(~bad)&df.buy.notna()&(df.date>='20180101')].reset_index(drop=True)
print(f"평가 대상 {len(D):,}행 · 폐지 {int((D.grp=='폐지').sum()):,}행 · 코스닥 60일선 위 {D.q60.mean()*100:.0f}%")
D.to_pickle("data/kd_feat.pkl"); print("saved data/kd_feat.pkl")
