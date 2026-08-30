# -*- coding: utf-8 -*-
"""2021~현재 · 모든 규칙 모든 거래 · 각 300만원 투입 시 손익"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
CASH=3_000_000
A=pd.read_csv("data/rules_trades_kospi.csv",dtype={"date":str,"ticker":str})
B=pd.read_csv("data/rules_trades_kosdaq.csv",dtype={"date":str,"ticker":str})
for x in (A,B): x.columns=[c.lstrip("\ufeff") for c in x.columns]
# D1 에 주가 1,000원 하한 반영
K=pd.read_pickle("data/kd_risk.pkl").set_index(["date","ticker"])[["close"]]
B=B.join(K,on=["date","ticker"])
n0=len(B); B=B[B.close.fillna(0)>=1000]
print(f"D1 주가 하한 반영: {n0} → {len(B)}건\n")
T=pd.concat([A,B],ignore_index=True)
T=T[(T.date>="20210101")].dropna(subset=["r"]).copy()
T["pnl"]=T.r/100*CASH
NAME={"P2":"P2 조정매집","P3":"P3 폭락반등","P4":"P4 조용한 신고가","D1":"D1 낙폭과대"}
ORDER=["P4","P2","P3","D1"]
print("# 2021-01-01 ~ 2026-08-28 · 거래당 300만원\n")
print("## 규칙별 총계\n")
print("| 규칙 | 보유 | 거래수 | 평균 | 중앙값 | 승률 | 최고 | 최악 | **총 손익** |")
print("|---|---|---|---|---|---|---|---|---|")
tot=0; n=0
for k in ORDER:
    s=T[T.R==k]
    if not len(s): continue
    tot+=s.pnl.sum(); n+=len(s)
    print(f"| {NAME[k]} | {int(s.hold.iloc[0])}일 | {len(s):,} | **{s.r.mean():+.2f}%** | {s.r.median():+.2f}% | "
          f"{(s.r>0).mean()*100:.0f}% | {s.r.max():+.0f}% | {s.r.min():.0f}% | **{s.pnl.sum()/1e4:+,.0f}만원** |")
print(f"| **합계** | | **{n:,}** | {T.r.mean():+.2f}% | {T.r.median():+.2f}% | {(T.r>0).mean()*100:.0f}% | | | **{tot/1e4:+,.0f}만원** |")
print(f"\n## 연도별 손익 (300만원씩)\n")
YS=list(range(2021,2027))
print("| 규칙 | "+" | ".join(str(y) for y in YS)+" | **합계** |")
print("|---|"+"---|"*(len(YS)+1))
for k in ORDER:
    s=T[T.R==k]; cells=[]
    for y in YS:
        g=s[s.y==y]
        cells.append(f"**{g.pnl.sum()/1e4:+,.0f}만**<br>{len(g)}건 · {g.r.mean():+.1f}%" if len(g) else "—")
    print(f"| {NAME[k]} | "+" | ".join(cells)+f" | **{s.pnl.sum()/1e4:+,.0f}만원** |")
cells=[]
for y in YS:
    g=T[T.y==y]
    cells.append(f"**{g.pnl.sum()/1e4:+,.0f}만**<br>{len(g)}건" if len(g) else "—")
print(f"| **전체** | "+" | ".join(cells)+f" | **{tot/1e4:+,.0f}만원** |")
print(f"\n## 필요 자금 (동시에 들고 있어야 하는 최대 금액)\n")
dates=sorted(T.date.unique()); DI={d:i for i,d in enumerate(dates)}
alld=sorted(set(T.date))
cnt=np.zeros(len(alld)+300)
for r in T.itertuples():
    i=DI[r.date]; cnt[i:i+int(r.hold)]+=1
mx=int(cnt.max()); md=int(np.median(cnt[cnt>0]))
print(f"- 모든 거래를 다 잡으려면 동시보유 최대 **{mx}종목** → 필요자금 **{mx*CASH/1e8:.1f}억원**")
print(f"- 중앙값 {md}종목 ({md*CASH/1e4:,.0f}만원)")
print(f"\n※ 위 손익은 '자금 무제한' 가정입니다. 계좌 3,000만원으로 실제 운용하면")
print(f"   규칙별 비중(P4 12 / P2 15 / P3 5 / D1 5)을 적용해 검증기간 연평균 +6.0% 수준입니다.")
