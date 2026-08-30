# -*- coding: utf-8 -*-
"""P4-B 운용 검증 — 손절/익절 스윕 + 동시보유 제한 포트폴리오 시뮬"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/bull_feat.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
g=D.groupby("ticker",sort=False); D["ret500"]=g.close.transform(lambda x:x/x.shift(500)-1)*100
dates=sorted(D.date.unique()); DI={d:i for i,d in enumerate(dates)}
M=((D.fromhi>=-10)&(D.r16<120)&(D.rw1<=120)&(D.fw5>=3)&(D.fw60>=1)&(D.vol20<=3)
   &(D.sr20<=1)&(D.ret20<=10)&(D.amt20>=50)&(~D.dil)&(D.ret500<=100)).fillna(False)
print(f"P4-B 신호 {int(M.sum()):,}건 · 폐지종목 {int((D[M].grp=='폐지').sum())}건\n")

# 경로 기반 손절/익절 — 보유 40일 동안 저가/고가 추적
H=40
hi=g.high.shift(-1).rolling(H,min_periods=1).max().shift(-(H-1))
lo=g.low.shift(-1).rolling(H,min_periods=1).min().shift(-(H-1))
D["hi40"],D["lo40"]=hi,lo
X=D[M].copy()
print("## 손절/익절 스윕 (40일 보유, 경로 근사)\n")
print("| 손절 | 익절 | 학습 | **검증** | 검증승률 | 검증PF | 최악 |\n|---|---|---|---|---|---|---|")
best=None
for st in (None,-8,-10,-15):
    for tg in (None,15,20,30):
        r=X.n40.values.astype(float).copy()
        if st is not None:
            hit=(X.lo40/X.buy-1)*100<=st
            r=np.where(hit, st-X.cost.values, r)
        if tg is not None:
            ht=((X.hi40/X.buy-1)*100>=tg)
            if st is not None: ht=ht&~hit
            r=np.where(ht, tg-X.cost.values, r)
        ok=np.isfinite(r); yy=X.y.values
        a=r[ok&(yy<=2022)]; b=r[ok&(yy>=2023)]
        if len(b)<50: continue
        pf=b[b>0].sum()/abs(b[b<=0].sum())
        print(f"| {st if st else '-'}% | {tg if tg else '-'}% | {a.mean():+.2f}% | **{b.mean():+.2f}%** | "
              f"{(b>0).mean()*100:.0f}% | {pf:.2f} | {b.min():+.0f}% |")

# ── 실제 운용 시뮬: 최대 동시보유 N, 자금 균등배분 ─────────────
print("\n## 실전 시뮬 — 자금 3,000만원 · 최대 동시보유 10종목 · 40일 보유\n")
X2=X.sort_values("date")
for CAPN,SEED in [(10,30_000_000)]:
    for lab,sub in [("전체 2018~26",X2),("검증 2023~26",X2[X2.y>=2023])]:
        cash=SEED; held={}; peak=eq=SEED; mdd=0; trades=[]
        for d in dates:
            if lab.startswith("검증") and d<"20230101": continue
            for t in [t for t,v in held.items() if v["out"]==d]:
                v=held.pop(t); cash+=v["amt"]*(1+v["r"]/100); trades.append(v["r"])
            todo=X2[(X2.date==d)]
            for row in todo.itertuples():
                if len(held)>=CAPN or row.ticker in held: continue
                if not np.isfinite(row.n40): continue
                amt=cash/max(CAPN-len(held),1)
                if amt<100000: continue
                oi=DI[d]+H
                held[row.ticker]={"amt":amt,"r":row.n40,"out":dates[min(oi,len(dates)-1)]}
                cash-=amt
            eq=cash+sum(v["amt"] for v in held.values())
            peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak*100)
        eq=cash+sum(v["amt"]*(1+v["r"]/100) for v in held.values())
        yrs=(len(dates) if not lab.startswith("검증") else 44*21)/246
        cagr=((eq/SEED)**(1/yrs)-1)*100
        print(f"- **{lab}**: 최종 {eq/1e4:,.0f}만원 (원금 {SEED/1e4:,.0f}만) · 총수익 **{(eq/SEED-1)*100:+.1f}%** · "
              f"연평균 **{cagr:+.1f}%** · 최대낙폭 {mdd:.1f}% · 거래 {len(trades)}건 승률 {np.mean([1 for t in trades if t>0])*len([t for t in trades if t>0])/max(len(trades),1)*100:.0f}%")
