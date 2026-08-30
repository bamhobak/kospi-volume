# -*- coding: utf-8 -*-
"""코스닥 폐지위험 2 — 폐지 예측 신호 탐색
   대상: D1 통과가 가능했던 종목(외국인 데이터 보유) 166개 폐지종목 vs 생존종목
   후보: DART 위험공시 · 거래대금 · 주가수준 · 장기수익률 · 외국인지분율
"""
import io,sys,sqlite3,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
c=sqlite3.connect("file:data/delisted_kd.db?mode=ro",uri=True,timeout=600)
DL=pd.read_sql("SELECT ticker,name,date,close,volume,frgn,foreign_ratio FROM daily WHERE date>='20180101' ORDER BY ticker,date",c);c.close()
c=sqlite3.connect("file:data/kosdaq.db?mode=ro",uri=True,timeout=600)
SV=pd.read_sql("SELECT ticker,name,date,close,volume,frgn,foreign_ratio FROM daily WHERE date>='20180101' ORDER BY ticker,date",c);c.close()
SV=SV[~SV.ticker.isin(set(DL.ticker))]
DL["grp"],SV["grp"]="폐지","생존"
lastd=DL.groupby("ticker").date.max().to_dict()
df=pd.concat([DL,SV],ignore_index=True)
g=df.sort_values(["ticker","date"]).groupby("ticker",sort=False)
df=df.sort_values(["ticker","date"]).reset_index(drop=True); g=df.groupby("ticker",sort=False)
df["amt20"]=(df.volume.astype(float)*df.close).groupby(df.ticker).transform(lambda x:x.rolling(20).mean())/1e8
df["ret250"]=g.close.transform(lambda x:x/x.shift(250)-1)*100
v60=g["volume"].transform(lambda x:x.rolling(60).sum()).replace(0,np.nan)
df["fw60"]=g["frgn"].transform(lambda x:x.fillna(0).rolling(60).sum())/v60*100
df["lastday"]=df.ticker.map(lastd)
dd=pd.to_datetime(df.date,format="%Y%m%d")
ld=pd.to_datetime(df.lastday,format="%Y%m%d",errors="coerce")
df["m2d"]=(ld-dd).dt.days/30.4
# ── DART 위험 공시 ────────────────────────────────────────────
d=sqlite3.connect("file:data/dart/disclosures.db?mode=ro",uri=True,timeout=300)
risk=pd.read_sql("""SELECT stock_code t, rcept_dt, report_nm FROM disclosure WHERE
    report_nm LIKE '%불성실공시%' OR report_nm LIKE '%감사보고서 제출 지연%'
    OR report_nm LIKE '%개선기간%' OR report_nm LIKE '%관리종목%'
    OR report_nm LIKE '%횡령%' OR report_nm LIKE '%배임%'
    OR report_nm LIKE '%소송%' OR report_nm LIKE '%회생절차%' OR report_nm LIKE '%파산%'
    OR report_nm LIKE '%감사의견%' OR report_nm LIKE '%거래정지%'""",d);d.close()
print(f"위험 공시 {len(risk):,}건 · {risk.t.nunique():,}종목\n")
from collections import defaultdict
RK=defaultdict(list)
for r in risk.itertuples(): RK[r.t].append(r.rcept_dt)
# 최근 12개월 내 위험공시 여부
flag=np.zeros(len(df),bool)
for t,idx in df.groupby("ticker").indices.items():
    L=pd.to_datetime(RK.get(t,[]),format="%Y%m%d",errors="coerce")
    if len(L)==0: continue
    x=dd.values[idx]
    for j,i in enumerate(idx):
        flag[i]=bool(((L.values>=x[j]-np.timedelta64(365,"D"))&(L.values<=x[j])).any())
df["riskDisc"]=flag
print("## 폐지 12개월 전 시점 vs 생존종목 — 지표 비교\n")
PRE=df[(df.grp=="폐지")&df.m2d.between(0,12)]
ALIVE=df[(df.grp=="생존")&(df.date>="20190101")]
print("| 지표 | 폐지 12개월 전 | 생존 종목 | 판별력 |\n|---|---|---|---|")
for k,lab,fn in [("riskDisc","최근1년 위험공시 있음",lambda x:x.mean()*100),
                 ("close","주가 1,000원 미만 비율",lambda x:(x<1000).mean()*100),
                 ("close","주가 2,000원 미만 비율",lambda x:(x<2000).mean()*100),
                 ("amt20","거래대금 2억 미만 비율",lambda x:(x<2).mean()*100),
                 ("amt20","거래대금 5억 미만 비율",lambda x:(x<5).mean()*100),
                 ("amt20","거래대금 10억 미만 비율",lambda x:(x<10).mean()*100),
                 ("ret250","1년수익 -50% 이하 비율",lambda x:(x<=-50).mean()*100),
                 ("ret250","1년수익 -70% 이하 비율",lambda x:(x<=-70).mean()*100),
                 ("foreign_ratio","외국인지분 1% 미만 비율",lambda x:(x<1).mean()*100),
                 ("fw60","외국인60일<1 비율",lambda x:(x<1).mean()*100)]:
    a=fn(PRE[k].dropna()); b=fn(ALIVE[k].dropna())
    print(f"| {lab} | **{a:.0f}%** | {b:.0f}% | {a-b:+.0f}%p |")
df.to_pickle("data/kd_risk.pkl")
print("\n저장: data/kd_risk.pkl")
