# -*- coding: utf-8 -*-
"""규칙별 1종목당 투입비중 산출 — 계좌 100 기준
   근거: (1) 켈리 기준(로그자산 기대값 최대화, 수치해) (2) 동시보유 실측 (3) 최악손실 방어
"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
A=pd.read_csv("data/rules_trades_kospi.csv",dtype={"date":str,"ticker":str})
B=pd.read_csv("data/rules_trades_kosdaq.csv",dtype={"date":str,"ticker":str})
T=pd.concat([A,B],ignore_index=True)
T.columns=[c.lstrip("\ufeff") for c in T.columns]
ORDER=["P2","P3","P4","D1"]
NAME={"P2":"P2 조정매집","P3":"P3 폭락반등","P4":"P4 조용한 신고가","D1":"D1 낙폭과대"}

def kelly(r):
    """E[log(1+f*r)] 최대화 — r 은 % 단위 수익률 배열"""
    x=np.asarray(r)/100.0
    lo,hi=0.0,1.0
    f=np.linspace(0.001,0.999,999)
    with np.errstate(divide="ignore",invalid="ignore"):
        g=np.array([np.mean(np.log1p(np.clip(fi*x,-0.999,None))) for fi in f])
    return f[np.nanargmax(g)], np.nanmax(g)

print("## 1) 규칙별 거래 통계 — 검증기간(2023~26) 기준\n")
print("| 규칙 | 보유 | 건수 | 평균 | 중앙값 | 표준편차 | 승률 | 최악 | 하위5% |\n|---|---|---|---|---|---|---|---|---|")
ST={}
for k in ORDER:
    v=T[(T.R==k)&(T.y>=2023)].r.dropna().values
    f=T[T.R==k]
    ST[k]=dict(v=v,hold=int(f.hold.iloc[0]),all=T[T.R==k].r.dropna().values)
    print(f"| {NAME[k]} | {ST[k]['hold']}일 | {len(v)} | **{v.mean():+.2f}%** | {np.median(v):+.2f}% | {v.std():.1f}%p | "
          f"{(v>0).mean()*100:.0f}% | {v.min():.1f}% | {np.percentile(v,5):.1f}% |")

print("\n## 2) 켈리 기준 — 한 종목에 계좌의 몇 %를 걸 때 장기 자산성장이 최대인가\n")
print("| 규칙 | 켈리(검증) | 켈리(전체기간) | **낮은 쪽** | 1/4 켈리 | 최악손실 시 계좌타격 |\n|---|---|---|---|---|---|")
for k in ORDER:
    kv,_=kelly(ST[k]["v"]); ka,_=kelly(ST[k]["all"])
    lo=min(kv,ka); q=lo/4
    print(f"| {NAME[k]} | {kv*100:.0f}% | {ka*100:.0f}% | **{lo*100:.0f}%** | {q*100:.1f}% | {q*ST[k]['v'].min():.1f}% |")
print("\n※ 켈리 원값은 파산 위험이 큽니다(추정오차·꼬리위험). 실무는 1/4~1/2 켈리를 씁니다.\n")

print("## 3) 동시보유 실측 — 모든 신호를 다 잡았다면 몇 종목을 동시에 들고 있었나\n")
print("| 규칙 | 평균 | 중앙값 | 90%분위 | **최대** | 최대 시점 |\n|---|---|---|---|---|---|")
alld=sorted(T.date.unique()); DI={d:i for i,d in enumerate(alld)}
CONC={}
for k in ORDER:
    f=T[T.R==k]; h=ST[k]["hold"]
    cnt=np.zeros(len(alld))
    for r in f.itertuples():
        i=DI[r.date]; cnt[i:min(i+h,len(alld))]+=1
    live=cnt[cnt>0] if (cnt>0).any() else np.array([0])
    CONC[k]=dict(mean=live.mean(),med=np.median(live),p90=np.percentile(live,90),mx=cnt.max(),
                 at=alld[int(np.argmax(cnt))])
    c=CONC[k]
    print(f"| {NAME[k]} | {c['mean']:.0f}종목 | {c['med']:.0f} | {c['p90']:.0f} | **{c['mx']:.0f}종목** | {c['at']} |")
print("\n## 4) 규칙끼리 동시에 터지는가 (같은 날 신호가 겹치는 정도)\n")
piv=T.groupby(["date","R"]).size().unstack(fill_value=0)
for k in ORDER:
    if k not in piv: piv[k]=0
print("| 규칙 | 신호 있는 날 | 다른 규칙과 겹친 날 | 겹침률 |\n|---|---|---|---|")
for k in ORDER:
    days=piv[piv[k]>0]
    ov=(days[[c for c in ORDER if c!=k]].sum(axis=1)>0).sum()
    print(f"| {NAME[k]} | {len(days)}일 | {ov}일 | {ov/max(len(days),1)*100:.0f}% |")
