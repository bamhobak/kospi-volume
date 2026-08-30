# -*- coding: utf-8 -*-
"""P4 보유기간 재검토 1 — 수익 누적 경로 + 기간별 성적 + '시간당 수익'
   40일이 긴가? 는 (1) 수익이 언제 쌓이는가 (2) 자본을 묶은 시간 대비 얼마인가 로 답한다.
"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/bull_feat.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
g=D.groupby("ticker",sort=False)
D["ret250"]=g.close.transform(lambda x:x/x.shift(250)-1)*100
D["above20"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
dates=sorted(D.date.unique()); DI={d:i for i,d in enumerate(dates)}
lastpos=g.date.transform("max").map(DI); lastclose=g.close.transform("last"); mypos=D.date.map(DI)
HZ=[1,2,3,5,7,10,12,15,20,25,30,35,40,50,60,80]
for h in HZ:
    if f"n{h}" in D: continue
    sell=g.close.shift(-h).where(~(mypos+h>lastpos), lastclose)
    D[f"n{h}"]=(sell/D.buy-1)*100-D.cost
M=(((D.fromhi>=-10)&(D.r16<120)&(D.rw1<=120)&(D.fw5>=3)&(D.fw60>=1)&(D.vol20<=3)
   &(D.sr20<=1)&(D.ret20<=10)&(D.amt20>=50)&(~D.dil)).fillna(False)
   & ~((D.above20>70)&(D.ret250>120)).fillna(False))
X=D[M].copy(); IS=X[X.y<=2022]; OS=X[X.y>=2023]
print(f"P4 신호 {len(X):,}건 (학습 {len(IS)} / 검증 {len(OS)})\n")
print("## 보유일수별 성적 — 검증기간(2023~26)이 실전 기대치\n")
print("| 보유 | 학습 평균 | **검증 평균** | 검증 중앙값 | 검증 승률 | 검증 PF | **검증 일당수익** | 연환산(246일) |")
print("|---|---|---|---|---|---|---|---|")
best=[]
for h in HZ:
    a=IS[f"n{h}"].dropna(); b=OS[f"n{h}"].dropna()
    if len(b)<50: continue
    r=b.values; pf=r[r>0].sum()/abs(r[r<=0].sum()) if (r<=0).any() else 99
    per=b.mean()/h; ann=per*246
    best.append((h,b.mean(),per,ann,pf,(r>0).mean()*100))
    print(f"| {h}일 | {a.mean():+.2f}% | **{b.mean():+.2f}%** | {np.median(b):+.2f}% | {(r>0).mean()*100:.0f}% | {pf:.2f} | **{per:+.3f}%** | {ann:+.1f}% |")
print("\n## 수익 누적 경로 (검증기간 평균, 매수가 대비)\n")
cum=[(h,OS[f"n{h}"].dropna().mean()) for h in HZ]
top=max(c[1] for c in cum)
print("```")
for h,v in cum:
    bar="█"*max(int(v/top*46),0) if v>0 else ""
    print(f"{h:>2}일 {v:+6.2f}%  {bar}")
print("```")
m40=OS.n40.dropna().mean()
for h in (10,15,20,25,30):
    v=OS[f"n{h}"].dropna().mean()
    print(f"- {h}일까지 40일 수익의 **{v/m40*100:.0f}%** 를 확보")
