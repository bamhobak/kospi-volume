# -*- coding: utf-8 -*-
"""시가총액·회전율·PBR 패널 (point-in-time)
   발행주식수는 사업보고서 기준, 기말 +105일 이후에만 사용(공시 전 정보 금지).
"""
import io,sys,re,sqlite3,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
c=sqlite3.connect("file:data/dart/shares.db?mode=ro",uri=True,timeout=300)
S=pd.read_sql("SELECT stock_code sc,year,se,issued,treasury,distb FROM shares WHERE reprt='11011'",c);c.close()
S["se"]=S.se.fillna("").str.replace(r"\s+","",regex=True)
S["kind"]=np.where(S.se.str.contains("보통")&~S.se.str.contains("보통주외|보통주외의"),0,
           np.where(S.se=="합계",1,2))
S=S[(S.kind<2)&(S.issued>0)].sort_values(["sc","year","kind"]).drop_duplicates(["sc","year"],keep="first")
S["avail"]=(pd.to_datetime(S.year.astype(str)+"1231")+pd.Timedelta(days=105)).dt.strftime("%Y%m%d")
S["a"]=S.avail.astype(int)
print(f"발행주식수 {len(S):,}행 · {S.sc.nunique():,}종목 · {S.year.min()}~{S.year.max()}")
def build(feat,fin,out,label):
    D=pd.read_pickle(feat)
    F=pd.read_pickle(fin).rename(columns={"sc":"ticker"})
    D=D.merge(F[["date","ticker","equity","부채비율","ROE","영업이익률","자본잠식"]],on=["date","ticker"],how="left")
    D["d"]=D.date.astype(int)
    D=pd.merge_asof(D.sort_values("d"),S.sort_values("a")[["sc","a","issued","treasury","distb"]],
                    left_on="d",right_by=None,right_on="a",left_by="ticker",right_index=False,
                    by=None,direction="backward") if False else \
      pd.merge_asof(D.sort_values("d"),S.rename(columns={"sc":"ticker"}).sort_values("a")[["ticker","a","issued","treasury","distb"]],
                    left_on="d",right_on="a",by="ticker",direction="backward")
    D["marcap"]=D.close*D.issued/1e8                       # 억원
    D["회전율"]=D.amt20/D.marcap*100                        # 일평균 거래대금 / 시총 (%)
    D["PBR"]=np.where(D.equity.fillna(0)>0,D.marcap*1e8/D.equity,np.nan)
    D["자사주"]=np.where(D.issued>0,D.treasury.fillna(0)/D.issued*100,np.nan)
    D["유통비중"]=np.where(D.issued>0,D.distb/D.issued*100,np.nan)
    cov=D[["marcap","회전율","PBR"]].notna().mean()*100
    print(f"{label}: 시총 {cov['marcap']:.0f}% · 회전율 {cov['회전율']:.0f}% · PBR {cov['PBR']:.0f}%")
    m=D.marcap.dropna()
    print(f"   시총 분위: 10% {np.percentile(m,10):,.0f}억 · 중앙 {np.median(m):,.0f}억 · 90% {np.percentile(m,90):,.0f}억")
    D.to_pickle(out)
build("data/bull_feat.pkl","data/kp_fin.pkl","data/kp_cap.pkl","코스피")
build("data/kd_feat.pkl","data/kq_fin.pkl","data/kq_cap.pkl","코스닥")
