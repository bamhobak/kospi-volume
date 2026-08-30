# -*- coding: utf-8 -*-
"""D1(코스닥 낙폭과대) 거래 분포 — 현재 사이트 정의 그대로"""
import io,sys,csv,sqlite3,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
import FinanceDataReader as fdr
IND={}
for r in csv.DictReader(open("data/industry.csv",encoding="utf-8-sig")):
    k=list(r.values()); IND[k[0]]=k[-1]
c=sqlite3.connect("file:data/kosdaq.db?mode=ro",uri=True,timeout=600)
df=pd.read_sql("""SELECT date,ticker,name,open,high,low,close,volume,frgn FROM daily
    WHERE close>0 AND date>='20170101' ORDER BY ticker,date""",c); c.close()
try:
    c=sqlite3.connect("file:data/delisted_kd.db?mode=ro",uri=True,timeout=600)
    dl=pd.read_sql("""SELECT date,ticker,name,open,high,low,close,volume,frgn FROM daily
        WHERE close>0 AND date>='20170101' ORDER BY ticker,date""",c); c.close()
    dl=dl[~dl.ticker.isin(set(df.ticker))]
    df=pd.concat([df,dl],ignore_index=True)
    print(f"폐지 {dl.ticker.nunique()}종목 포함")
except Exception as e: print("폐지 DB 없음:",str(e)[:60])
df=df[df.ticker.str.endswith("0")].sort_values(["ticker","date"]).reset_index(drop=True)
dates=sorted(df.date.unique()); DI={d:i for i,d in enumerate(dates)}
print(f"코스닥 {df.ticker.nunique():,}종목 {len(df):,}행 {dates[0]}~{dates[-1]}")
g=df.groupby("ticker",sort=False)
V,C=df.volume.astype(float),df.close
df["ret20"]=g.close.transform(lambda x:x/x.shift(20)-1)*100
df["ret60"]=g.close.transform(lambda x:x/x.shift(60)-1)*100
a20=g["volume"].transform(lambda x:x.shift(1).rolling(20).mean())
df["vs1"]=V/a20
v60=g["volume"].transform(lambda x:x.rolling(60).sum()).replace(0,np.nan)
df["fw60"]=g["frgn"].transform(lambda x:x.fillna(0).rolling(60).sum())/v60*100
df["amt20"]=(V*C).groupby(df.ticker).transform(lambda x:x.rolling(20).mean())/1e8
# 공매도
SF={}
try:
    by={}
    for r in csv.DictReader(open("data/kosdaq_short_recent.csv",encoding="utf-8")):
        try: by.setdefault(r["ticker"],[]).append((r["date"],float(r["short_ratio"])))
        except: pass
except Exception: by={}
k=sqlite3.connect("file:data/kis/market.db?mode=ro",uri=True,timeout=300)
ss=pd.read_sql("SELECT date,ticker,short_ratio FROM short_sale WHERE short_ratio IS NOT NULL ORDER BY ticker,date",k);k.close()
ss=ss[ss.ticker.isin(set(df.ticker))]
gs=ss.groupby("ticker").short_ratio
ss["srd"]=gs.transform(lambda x:x.rolling(5).mean())<gs.transform(lambda x:x.rolling(20).mean())
df=df.merge(ss[["date","ticker","srd"]],on=["date","ticker"],how="left")
print(f"공매도 매칭 {df.srd.notna().mean()*100:.0f}%")
# 증자
from collections import defaultdict
d=sqlite3.connect("file:data/dart/disclosures.db?mode=ro",uri=True,timeout=300)
dz=pd.read_sql("""SELECT stock_code t, rcept_dt FROM disclosure WHERE
   replace(report_nm,' ','') LIKE '%유상증자결정%' OR replace(report_nm,' ','') LIKE '%전환사채권발행결정%'
   OR replace(report_nm,' ','') LIKE '%신주인수권부사채권발행결정%'""",d);d.close()
DIL=defaultdict(list)
for r in dz.itertuples(): DIL[r.t].append(r.rcept_dt)
ds=pd.to_datetime(df.date); dil=np.zeros(len(df),bool)
for t,idx in df.groupby("ticker").indices.items():
    L=pd.to_datetime(DIL.get(t,[]))
    if len(L)==0: continue
    for i,x in zip(idx,ds.values[idx]):
        dil[i]=bool(((L.values>=x-np.timedelta64(90,"D"))&(L.values<=x)).any())
df["dil"]=dil
# 업종 60일
df["up"]=df.ticker.map(IND)
u=df[df.up.notna()].dropna(subset=["ret60"]).groupby(["date","up"]).ret60.median()
df["sr60"]=pd.MultiIndex.from_arrays([df.date,df.up]).map(u)
# 코스피 지수 60일선
ki=fdr.DataReader("KS11","2016-06-01"); ki=ki[ki.Close>0]; ki.index=ki.index.strftime("%Y%m%d")
kc=ki["Close"].reindex(dates).ffill()
df["k60"]=df.date.map(kc>kc.rolling(60).mean()).fillna(False).values
df["kok"]=df.date.map(kc.notna()).fillna(False).values
# 비용(코스닥 한 단계 위) · 불연속 · 청산
df["cost"]=0.18+np.select([df.amt20>=100,df.amt20>=50,df.amt20>=20,df.amt20>=10],[.30,.50,.70,1.00],default=1.30)
pc=g.close.shift(1); jj=(C/pc).where(pc>0); badday=((jj>1.32)|(jj<0.68)).fillna(False)
bad=np.zeros(len(df),bool); pos=df.date.map(DI).values
for t,sub in df[badday].groupby("ticker"):
    idx=df.index[df.ticker==t].values
    bp=np.sort([DI[x] for x in sub.date if x in DI]); p=pos[idx]
    q=np.searchsorted(bp,p,side="right")
    bad[idx[(q<len(bp))&(bp[np.minimum(q,len(bp)-1)]-p<=42)]]=True
df["buy"]=g.open.shift(-1)
lastpos=g.date.transform("max").map(DI); lastclose=g.close.transform("last"); mypos=df.date.map(DI)
sell=g.close.shift(-20).where(~(mypos+20>lastpos),lastclose)
df["r"]=(sell/df.buy-1)*100-df.cost
df["y"]=df.date.str[:4].astype(int)
M=((df.ret20<=-20)&(df.vs1>=2)&(df.fw60>=1)&(df.amt20>=2)&(~df.k60)&df.kok
   &(df.sr60.isna()|(df.sr60<=-15))&(df.srd==True)&(~df.dil)&(~bad)&df.buy.notna()
   &(df.date>='20180101')).fillna(False)
T=df[M].copy(); T["R"]="D1"; T["hold"]=20
print(f"\nD1: {len(T):,}건 (검증 {len(T[T.y>=2023]):,}건) · 전체 평균 {T.r.mean():+.2f}% 검증 {T[T.y>=2023].r.mean():+.2f}%")
T[["R","date","ticker","name","y","r","hold","k60"]].dropna(subset=["r"]).to_csv("data/rules_trades_kosdaq.csv",index=False,encoding="utf-8-sig")
print("저장: data/rules_trades_kosdaq.csv")
