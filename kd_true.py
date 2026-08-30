# -*- coding: utf-8 -*-
"""'진짜 부실 폐지'만 골라 방어조건 검증
   폐지에는 합병·자진상장폐지·이전상장·SPAC 합병·펀드 만기가 섞여 있다(주주 손실 없음).
   구분: 폐지 직전 12개월 주가 흐름 — 부실은 폭락하고, 합병·자진폐지는 유지되거나 오른다.
"""
import io,sys,sqlite3,re,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
c=sqlite3.connect("file:data/delisted_kd.db?mode=ro",uri=True,timeout=600)
d=pd.read_sql("SELECT ticker,name,date,close,volume,frgn FROM daily WHERE date>='20180101' ORDER BY ticker,date",c);c.close()
d=d.sort_values(["ticker","date"]).reset_index(drop=True)
g=d.groupby("ticker",sort=False)
last=g.date.max().to_dict(); d["lastday"]=d.ticker.map(last)
dd=pd.to_datetime(d.date,format="%Y%m%d"); ld=pd.to_datetime(d.lastday,format="%Y%m%d")
d["m2d"]=(ld-dd).dt.days/30.4
# 종목 분류
info=[]
for (t,n),gg in d.groupby(["ticker","name"]):
    gg=gg.sort_values("date")
    endpx=gg.close.iloc[-1]
    ref=gg[gg.m2d.between(11,13)].close
    px12=ref.iloc[0] if len(ref) else np.nan
    chg=(endpx/px12-1)*100 if px12==px12 and px12 else np.nan
    kind=("SPAC" if "기업인수목적" in n else
          "펀드" if re.search(r"투자회사|특별자산|리츠|부동산투자|자원개발",n) else
          "일반")
    info.append((t,n,kind,endpx,chg,gg.close.median()))
I=pd.DataFrame(info,columns=["ticker","name","kind","endpx","chg12","medpx"])
I["distress"]=(I.kind=="일반")&((I.chg12<=-50)|(I.endpx<1000))
print("## 폐지 493종목 분류\n")
print("| 유형 | 종목수 | 폐지 직전 주가 중앙 | 최근1년 등락 중앙 |\n|---|---|---|---|")
for lab,m in [("SPAC(합병으로 소멸)",I.kind=="SPAC"),("펀드·리츠(만기)",I.kind=="펀드"),
              ("**진짜 부실 폐지**",I.distress),("일반 - 합병·자진폐지 등",(I.kind=="일반")&~I.distress)]:
    s=I[m]
    print(f"| {lab} | {len(s)} | {s.endpx.median():,.0f}원 | {s.chg12.median():+.0f}% |")
DIS=set(I[I.distress].ticker)
print(f"\n진짜 부실 폐지 {len(DIS)}종목 (전체 493의 {len(DIS)/493*100:.0f}%)\n")
# 부실 종목에 대해 D1 시세조건 통과 + 방어조건 효과
d["amt20"]=(d.volume.astype(float)*d.close).groupby(d.ticker).transform(lambda x:x.rolling(20).mean())/1e8
d["ret20"]=g.close.transform(lambda x:x/x.shift(20)-1)*100
d["ret250"]=g.close.transform(lambda x:x/x.shift(250)-1)*100
a20=g["volume"].transform(lambda x:x.shift(1).rolling(20).mean())
d["vs1"]=d.volume/a20
P=d[d.ticker.isin(DIS)&d.m2d.between(0,24)]
base=((P.ret20<=-20)&(P.vs1>=2)&(P.amt20>=2)).fillna(False)
print("## 진짜 부실 폐지 종목의 D1 통과 — 방어조건 효과\n")
print("| 조건 | 통과 신호 | 감소율 | 통과 종목수 |\n|---|---|---|---|")
n0=int(base.sum())
for nm,m in [("현행(거래대금 2억)",pd.Series(True,index=P.index)),
             ("주가 ≥ 500원",P.close>=500),("주가 ≥ 1,000원",P.close>=1000),
             ("주가 ≥ 2,000원",P.close>=2000),
             ("주가 ≥ 1,000 + 1년수익 > -70%",(P.close>=1000)&(P.ret250>-70)),
             ("거래대금 ≥ 10억",P.amt20>=10)]:
    m=m.fillna(False) if hasattr(m,"fillna") else m
    k=base&m
    print(f"| {nm} | {int(k.sum())}건 | {(1-k.sum()/max(n0,1))*100:.0f}% | {P[k].ticker.nunique()}종목 |")
print("\n## 남는 부실 종목 (주가 ≥ 1,000원 적용 후)\n")
k=base&(P.close>=1000).fillna(False)
if int(k.sum()):
    print("| 종목 | 신호 | 폐지일 | 주가 중앙 |\n|---|---|---|---|")
    for (t,n),gg in P[k].groupby(["ticker","name"]):
        print(f"| {n} | {len(gg)}건 | {gg.lastday.iloc[0]} | {gg.close.median():,.0f}원 |")
