# -*- coding: utf-8 -*-
"""게이트 조이기 — 계좌 수익금으로 판정.

규칙 단위로는 [폭락반등]·[낙폭과대]·[자사주 낙폭] 이 좁힐수록 좋아졌다. 그러나
신호가 줄면 자리가 비고 다른 규칙이 들어오므로 계좌로 봐야 실제 이득을 안다.
지난 두 번(추가매수·업종붕괴 완화)에서 배운 대로 같은 시드끼리 짝지어 비교하고,
자리 제한 착시를 피하려 비중을 키우고 줄여도 결론이 유지되는지 본다.
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
src = (BASE/"portfolio.py").read_text(encoding="utf-8")
ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, KB, RULES = ns["KP"], ns["KQ"], ns["KB"], ns["RULES"]
import FinanceDataReader as fdr
parts = [fdr.DataReader("KS11", a, b) for a,b in (("2015-01-01","2019-12-31"),("2020-01-01","2026-09-03"))]
IX = pd.concat(parts); IX = IX[~IX.index.duplicated()].sort_index(); IX = IX[IX.Close>0]
IX["d"] = IX.index.strftime("%Y%m%d")
DEV = dict(zip(IX.d, (IX.Close/IX.Close.rolling(60).mean()-1)*100))
for K in (KP, KQ, KB): K["kdev"] = K.date.map(DEV)
adates = sorted(set(KP.date)|set(KQ.date)); ADI = {d:i for i,d in enumerate(adates)}

def build(R):
    sig=[]
    for rid,(K,hold,stop,pct,mx,cond) in R.items():
        g=K.groupby("ticker",sort=False); ex=g.close.shift(-hold)
        lo=g.low.shift(-1).rolling(hold,min_periods=1).min().shift(-(hold-1))
        X=K[cond.fillna(False)].copy()
        X["rid"],X["hold"]=rid,hold; X["stop"]=stop if stop else np.nan
        X["pct"],X["mx"]=pct,mx
        X["exit"]=ex.reindex(X.index); X["low"]=lo.reindex(X.index)
        sig.append(X[["date","ticker","rid","hold","stop","pct","mx","buy","exit","low","cost"]])
    S=pd.concat(sig).dropna(subset=["buy","exit","cost"]); S=S[S.buy>0].copy()
    S["di"]=S.date.map(ADI); return S.sort_values(["di","rid"]).reset_index(drop=True)

def sim(S, ds, seed=None):
    eq=1.0; op=[]; curve=[]; wins=[]
    lo_i,hi_i=ADI[ds[0]],ADI[ds[-1]]
    by={i:g for i,g in S[(S.di>=lo_i)&(S.di<=hi_i)].groupby("di")}
    rng=np.random.default_rng(seed) if seed is not None else None
    for d in ds:
        i=ADI[d]; st=[]
        for p in op:
            if p["ex"]<=i:
                hit=(p["stop"]==p["stop"]) and (p["low"]/p["buy"]-1)*100<=-p["stop"]*100
                r=(-p["stop"]*100-p["cost"]) if hit else ((p["exit"]/p["buy"]-1)*100-p["cost"])
                eq+=p["amt"]*r/100; wins.append(r>0)
            else: st.append(p)
        op=st; td=by.get(i)
        if td is not None:
            if rng is not None: td=td.sample(frac=1,random_state=int(rng.integers(1<<31)))
            inv=sum(p["amt"] for p in op)
            for t in td.itertuples():
                nr=sum(1 for p in op if p["rid"]==t.rid); w=eq*t.pct/100
                if nr>=t.mx or inv+w>eq or any(p["tk"]==t.ticker for p in op): continue
                op.append(dict(rid=t.rid,tk=t.ticker,buy=t.buy,exit=t.exit,low=t.low,
                               cost=t.cost,stop=t.stop,amt=w,ex=i+t.hold)); inv+=w
        curve.append(eq)
    C=pd.Series(curve); dd=(C/C.cummax()-1)*100
    return dict(nav=C.iloc[-1], mdd=dd.min(), win=np.mean(wins)*100 if wins else np.nan)

def with_gate(rid, thr):
    """그 규칙의 조건에 '코스피 60일선 이격 <= thr' 를 덧붙인다."""
    K,hold,stop,pct,mx,cond = RULES[rid]
    return (K,hold,stop,pct,mx, cond & (K.kdev<=thr))
CAND = [("현재 그대로", {}),
        ("폭락반등 -8", {"P3":-8}), ("폭락반등 -12", {"P3":-12}),
        ("낙폭과대 -8", {"D1":-8}), ("낙폭과대 -12", {"D1":-12}),
        ("자사주 -5", {"P5":-5}),
        ("셋 함께(-8/-8/-5)", {"P3":-8,"D1":-8,"P5":-5}),
        ("셋 함께(-12/-12/-5)", {"P3":-12,"D1":-12,"P5":-5})]
PERIODS=[("전체","20180101","20991231"),("학습","20180101","20221231"),
         ("검증","20230101","20991231"),("붐제외","20180101","20241231")]
SEEDS=12
print(f"  계좌 수익금 (시드 {SEEDS}회 · 같은 시드끼리 짝지어 · 괄호는 현재를 이긴 비율)\n")
print(f"  {'조건':<20}"+"".join(f"{p[0]:>17}" for p in PERIODS)+f"{'낙폭':>8}")
REF=None
for nm,gates in CAND:
    R=dict(RULES)
    for rid,thr in gates.items(): R[rid]=with_gate(rid,thr)
    S=build(R); cols=[]
    for _,d0,d1 in PERIODS:
        ds=[d for d in adates if d0<=d<=d1]
        cols.append([sim(S,ds,seed=k) for k in range(SEEDS)])
    if REF is None: REF=cols
    line=""
    for i,c in enumerate(cols):
        m=np.median([x["nav"] for x in c])
        w=np.mean([a["nav"]>b["nav"] for a,b in zip(c,REF[i])])*100
        line += f"{m:>10.2f}배      " if nm==CAND[0][0] else f"{m:>10.2f}배({w:>3.0f}%)"
    print(f"  {nm:<20}{line}{np.median([x['mdd'] for x in cols[0]]):>7.1f}%")
