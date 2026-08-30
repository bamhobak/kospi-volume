# -*- coding: utf-8 -*-
"""SG증권 사태 종목의 지문 찾기 — P4 신호 중 이들만 골라내는 최소침습 조건 탐색
   2023-04-24 무더기 하한가 8종목: 삼천리·서울가스·대성홀딩스·세방·다올투자증권·하림지주·선광·다우데이타
"""
import io,sys,sqlite3,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/bull_feat.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
g=D.groupby("ticker",sort=False)
# ── 추가 후보 지표 ────────────────────────────────────────────
D["ret250"]=g.close.transform(lambda x:x/x.shift(250)-1)*100
D["ret500"]=g.close.transform(lambda x:x/x.shift(500)-1)*100
D["vol60"]=g.close.transform(lambda x:(x/x.shift(1)-1).rolling(60).std())*100
D["vol250"]=g.close.transform(lambda x:(x/x.shift(1)-1).rolling(250).std())*100
# 1년 최대낙폭 (고점 대비 최저)
def mdd(x):
    r=x.rolling(250,min_periods=60)
    return (x/r.max()-1)*100
D["dd250"]=g.close.transform(lambda x:(x/x.rolling(250,min_periods=60).max()-1)*100)
D["mdd250"]=g.close.transform(lambda x:((x/x.rolling(250,min_periods=60).max()-1)*100).rolling(250,min_periods=60).min())
# 위험조정수익: 1년 수익 / 1년 변동성
D["sharpe250"]=D.ret250/(D.vol250*np.sqrt(250)).replace(0,np.nan)
D["sharpe500"]=D.ret500/(D.vol250*np.sqrt(250)).replace(0,np.nan)
# 20일선 위에 머문 비율 (추세 지속성)
D["above20"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
# 회전율: 20일 거래대금 / 시가총액
c=sqlite3.connect("file:data/kospi.db?mode=ro",uri=True,timeout=300)
mc=pd.read_sql("SELECT date,ticker,marcap FROM daily WHERE marcap IS NOT NULL AND marcap>0",c); c.close()
D=D.merge(mc,on=["date","ticker"],how="left")
D["turn"]=D.amt20*1e8/D.marcap*100          # 일평균 거래대금 / 시총 (%)
print(f"시가총액 확보: {D.marcap.notna().mean()*100:.0f}% 행\n")

SG={"004690":"삼천리","017390":"서울가스","016710":"대성홀딩스","004360":"세방",
    "030210":"다올투자증권","003380":"하림지주","003100":"선광","032190":"다우데이타"}
BASE=((D.fromhi>=-10)&(D.r16<120)&(D.rw1<=120)&(D.fw5>=3)&(D.fw60>=1)&(D.vol20<=3)
      &(D.sr20<=1)&(D.ret20<=10)&(D.amt20>=50)&(~D.dil)).fillna(False)     # ret500 가드 제거한 P4
X=D[BASE].copy()
X["isSG"]=X.ticker.isin(SG)&(X.y==2023)
S=X[X.isSG]; O=X[~X.isSG]
print(f"가드 없는 P4 신호 {len(X):,}건 = SG {len(S)}건 + 나머지 {len(O):,}건")
print(f"SG 평균 {S.n40.mean():+.1f}% · 나머지 평균 {O.n40.mean():+.2f}%\n")
print("## SG 종목 vs 나머지 — 지표 분포 비교\n")
print("| 지표 | SG 중앙값 | SG 최소 | SG 최대 | 나머지 중앙값 | 나머지 10%분위 | 나머지 90%분위 |\n|---|---|---|---|---|---|---|")
for k,lab in [("ret250","1년수익"),("ret500","2년수익"),("vol250","1년변동성"),("mdd250","1년최대낙폭"),
              ("sharpe250","1년 위험조정수익"),("sharpe500","2년 위험조정수익"),("above20","20일선 위 비율"),
              ("turn","회전율(거래대금/시총)"),("fromlo","저점대비"),("marcap","시가총액")]:
    a=S[k].dropna(); b=O[k].dropna()
    if not len(a): continue
    sc=1e8 if k=="marcap" else 1
    print(f"| {lab} | **{np.median(a)/sc:,.1f}** | {a.min()/sc:,.1f} | {a.max()/sc:,.1f} | {np.median(b)/sc:,.1f} | {np.percentile(b,10)/sc:,.1f} | {np.percentile(b,90)/sc:,.1f} |")
X.to_pickle("data/sg_x.pkl")
