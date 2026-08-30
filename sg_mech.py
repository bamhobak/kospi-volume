# -*- coding: utf-8 -*-
"""가드가 'SG 8종목'이 아니라 '기전'을 잡는지 검증
   1) P4 신호 중 SG 아닌 고위험조정수익 종목도 성적이 나쁜가
   2) 코스피 전체(규칙 무관)에서도 고위험조정수익 = 이후 수익 저조인가
   3) 임계값을 어디에 둬야 여유가 남는가
"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
X=pd.read_pickle("data/sg_x.pkl")
O=X[~X.isSG]
print("## 1) P4 신호 중 SG 를 뺀 나머지 — 위험조정수익 구간별 성적\n")
print("| 1년 위험조정수익 | 건수 | 평균 | 중앙값 | 승률 | 최악 |\n|---|---|---|---|---|---|")
bins=[(-99,1),(1,2),(2,3),(3,4),(4,6),(6,99)]
for lo,hi in bins:
    s=O[(O.sharpe250>lo)&(O.sharpe250<=hi)].n40.dropna()
    if len(s)<5: print(f"| {lo}~{hi} | {len(s)} | - | - | - | - |"); continue
    print(f"| {lo}~{hi} | {len(s)} | **{s.mean():+.2f}%** | {np.median(s):+.2f}% | {(s>0).mean()*100:.0f}% | {s.min():.1f}% |")

D=pd.read_pickle("data/bull_feat.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
g=D.groupby("ticker",sort=False)
D["ret250"]=g.close.transform(lambda x:x/x.shift(250)-1)*100
D["vol250"]=g.close.transform(lambda x:(x/x.shift(1)-1).rolling(250).std())*100
D["sharpe250"]=D.ret250/(D.vol250*np.sqrt(250)).replace(0,np.nan)
D["above20"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
SG={"004690","017390","016710","004360","030210","003380","003100","032190"}
U=D[~(D.ticker.isin(SG)&(D.y==2023))]          # SG 사건 제외한 코스피 전체
print("\n## 2) 코스피 전체(SG 제외·규칙 무관) — 위험조정수익 구간별 이후 40일 수익\n")
print("| 1년 위험조정수익 | 표본 | 학습(18~22) | 검증(23~26) | 전체 승률 |\n|---|---|---|---|---|")
for lo,hi in bins:
    s=U[(U.sharpe250>lo)&(U.sharpe250<=hi)]
    a=s[s.y<=2022].n40.dropna(); b=s[s.y>=2023].n40.dropna(); t=s.n40.dropna()
    if len(t)<200: continue
    print(f"| {lo}~{hi} | {len(t):,} | {a.mean():+.2f}% | {b.mean():+.2f}% | {(t>0).mean()*100:.0f}% |")

print("\n## 3) 임계값 여유 — SG 이후에도 통할 조건인가\n")
S=X[X.isSG]
print(f"- SG 8종목의 1년 위험조정수익: 최소 **{S.sharpe250.min():.1f}** / 중앙 {S.sharpe250.median():.1f} / 최대 {S.sharpe250.max():.1f}")
print(f"- SG 8종목의 20일선 위 비율: 최소 **{S.above20.min():.1f}%** / 중앙 {S.above20.median():.1f}%")
print(f"- 나머지 P4 신호 분위: 위험조정 90% {np.percentile(O.sharpe250.dropna(),90):.1f} · 95% {np.percentile(O.sharpe250.dropna(),95):.1f} · 99% {np.percentile(O.sharpe250.dropna(),99):.1f}")
print(f"- 나머지 P4 신호 분위: 20일선위 90% {np.percentile(O.above20.dropna(),90):.1f}% · 95% {np.percentile(O.above20.dropna(),95):.1f}% · 99% {np.percentile(O.above20.dropna(),99):.1f}%")
print("\n## 4) 코스피 전체에서 각 임계값에 걸리는 종목수 (과도한 배제 여부)\n")
print("| 조건 | 코스피 전체 배제율 | P4 신호 배제율 |\n|---|---|---|")
for nm,uc,xc in [("위험조정 > 3",U.sharpe250>3,O.sharpe250>3),("위험조정 > 4",U.sharpe250>4,O.sharpe250>4),
                 ("위험조정 > 5",U.sharpe250>5,O.sharpe250>5),("20일선위 > 75%",U.above20>75,O.above20>75),
                 ("20일선위 > 70%",U.above20>70,O.above20>70),("2년수익 > 100%",None,None)]:
    if uc is None: continue
    print(f"| {nm} | {uc.fillna(False).mean()*100:.1f}% | {xc.fillna(False).mean()*100:.1f}% |")
