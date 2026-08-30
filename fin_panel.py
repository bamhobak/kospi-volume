# -*- coding: utf-8 -*-
"""재무 지표를 '그 시점에 알 수 있었던 값'으로만 붙인다 (point-in-time).
   공시 시차: 1·3분기 +45일, 반기 +45일, 사업보고서 +90일. 여유 15일 추가.
   재무상태표(자본·부채)는 최신 분기, 손익(ROE·영업이익률·성장률)은 사업보고서 기준.
"""
import io,sys,sqlite3,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
c=sqlite3.connect("file:data/dart/financials.db?mode=ro",uri=True,timeout=600)
q="""SELECT stock_code sc, year, reprt, fs_div,
     max(CASE WHEN account='자본총계' THEN amount END) equity,
     max(CASE WHEN account='부채총계' THEN amount END) debt,
     max(CASE WHEN account='자산총계' THEN amount END) asset,
     max(CASE WHEN account='당기순이익(손실)' THEN amount END) ni,
     max(CASE WHEN account='매출액' THEN amount END) rev,
     max(CASE WHEN account IN ('영업이익','영업이익(손실)') THEN amount END) op
   FROM fin GROUP BY 1,2,3,4"""
D=pd.read_sql(q,c); c.close()
# 연결 우선, 없으면 별도
D["pri"]=(D.fs_div!="CFS").astype(int)
D=D.sort_values(["sc","year","reprt","pri"]).drop_duplicates(["sc","year","reprt"],keep="first")
# 공시 가능 시점
END={"11013":"0331","11012":"0630","11014":"0930","11011":"1231"}
LAG={"11013":60,"11012":60,"11014":60,"11011":105}
def avail(r):
    e=pd.Timestamp(f"{r.year}{END[r.reprt]}")
    return (e+pd.Timedelta(days=LAG[r.reprt])).strftime("%Y%m%d")
D["avail"]=[avail(r) for r in D.itertuples()]
print(f"재무 {len(D):,}행 · {D.sc.nunique():,}종목")
print("공시 가능 시점 예시:", D[D.year==2020].groupby("reprt").avail.first().to_dict())
# ── 재무상태표 지표 (최신 분기) ────────────────────────────────
B=D[D.equity.notna()&(D.equity!=0)].copy()
B["부채비율"]=B.debt/B.equity.abs()*100
B["자본잠식"]=(B.equity<0).astype(int)
B["자본자산"]=B.equity/B.asset.replace(0,np.nan)*100      # 자기자본비율
BS=B[["sc","avail","부채비율","자본잠식","자본자산","equity"]].sort_values(["sc","avail"])
# ── 손익 지표 (사업보고서 = 연간) ──────────────────────────────
A=D[(D.reprt=="11011")].copy().sort_values(["sc","year"])
A["ROE"]=A.ni/A.equity.abs().replace(0,np.nan)*100
A["영업이익률"]=np.where(A.rev.fillna(0)>0,A.op/A.rev*100,np.nan)
g=A.groupby("sc")
A["매출성장"]=g.rev.pct_change(fill_method=None)*100
A["영업이익성장"]=np.where((g.op.shift(1).fillna(0)>0),(A.op/g.op.shift(1)-1)*100,np.nan)
A["흑자전환"]=((A.ni>0)&(g.ni.shift(1)<0)).astype(int)
A["연속흑자"]=g.ni.transform(lambda x:(x>0).rolling(3,min_periods=3).sum())
IS=A[["sc","avail","ROE","영업이익률","매출성장","영업이익성장","흑자전환","연속흑자"]].sort_values(["sc","avail"])
print(f"재무상태표 패널 {len(BS):,} · 손익 패널 {len(IS):,}")
def attach(featpath,out,label):
    F=pd.read_pickle(featpath)[["date","ticker"]].drop_duplicates().sort_values(["date"])
    F=F.rename(columns={"ticker":"sc"}); F["d"]=F.date.astype(int)
    r=F
    for P,cols in ((BS,["부채비율","자본잠식","자본자산","equity"]),(IS,["ROE","영업이익률","매출성장","영업이익성장","흑자전환","연속흑자"])):
        p=P.dropna(subset=["avail"]).copy(); p["a"]=p.avail.astype(int)
        r=pd.merge_asof(r.sort_values("d"),p.sort_values("a")[["sc","a"]+cols],
                        left_on="d",right_on="a",by="sc",direction="backward")
        r=r.drop(columns=["a"])
    cov=r[["부채비율","ROE"]].notna().mean()*100
    print(f"{label}: {len(r):,}행 · 부채비율 채움 {cov['부채비율']:.0f}% · ROE 채움 {cov['ROE']:.0f}%")
    r.to_pickle(out)
attach("data/bull_feat.pkl","data/kp_fin.pkl","코스피")
attach("data/kd_feat.pkl","data/kq_fin.pkl","코스닥")
