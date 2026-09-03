# -*- coding: utf-8 -*-
"""[업종붕괴 이탈] 완화안 — 계좌 수익금으로 판정.

규칙 단위로는 완화할수록 평균이 떨어지지만 건수가 늘어 총량은 오히려 커진다.
어느 쪽이 실제로 이득인지는 계좌로만 알 수 있다 — 자리는 한정돼 있고, 신호가
한 시기에 몰리면 그때 다 사지도 못한다. 분산이 실제 체결을 늘리는지 본다.
기간을 갈라 같은 시드끼리 짝지어 비교한다.
"""
import io, sys, gc
from pathlib import Path
import numpy as np, pandas as pd
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
src = (BASE / "portfolio.py").read_text(encoding="utf-8")
ns = {"__file__": str(BASE / "portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES = ns["KP"], ns["KQ"], ns["RULES"]
base, dn60 = ns["base"], ns["dn60"]
adates = sorted(set(KP.date) | set(KQ.date)); ADI = {d: i for i, d in enumerate(adates)}
CORE = base(KP, 10) & dn60(KP) & (KP.srd == True) & (KP.close >= 1000)
cond_of = lambda u, dma, mdd: CORE & (KP.u <= u) & (KP.dma20 <= dma) & (KP.mdd60 <= mdd)

def build(R):
    sig = []
    for rid, (K, hold, stop, pct, mx, cond) in R.items():
        g = K.groupby("ticker", sort=False); ex = g.close.shift(-hold)
        lo = g.low.shift(-1).rolling(hold, min_periods=1).min().shift(-(hold - 1))
        X = K[cond.fillna(False)].copy()
        X["rid"], X["hold"] = rid, hold
        X["stop"] = stop if stop else np.nan
        X["pct"], X["mx"] = pct, mx
        X["exit"] = ex.reindex(X.index); X["low"] = lo.reindex(X.index)
        sig.append(X[["date","ticker","rid","hold","stop","pct","mx","buy","exit","low","cost"]])
    S = pd.concat(sig).dropna(subset=["buy","exit","cost"]); S = S[S.buy > 0].copy()
    S["di"] = S.date.map(ADI); return S.sort_values(["di","rid"]).reset_index(drop=True)

def sim(S, ds, seed=None):
    eq = 1.0; op = []; curve = []; n4 = 0
    lo_i, hi_i = ADI[ds[0]], ADI[ds[-1]]
    by = {i: g for i, g in S[(S.di >= lo_i) & (S.di <= hi_i)].groupby("di")}
    rng = np.random.default_rng(seed) if seed is not None else None
    for d in ds:
        i = ADI[d]; st = []
        for p in op:
            if p["ex"] <= i:
                hit = (p["stop"] == p["stop"]) and (p["low"]/p["buy"]-1)*100 <= -p["stop"]*100
                r = (-p["stop"]*100 - p["cost"]) if hit else ((p["exit"]/p["buy"]-1)*100 - p["cost"])
                eq += p["amt"] * r / 100
            else: st.append(p)
        op = st; td = by.get(i)
        if td is not None:
            if rng is not None: td = td.sample(frac=1, random_state=int(rng.integers(1 << 31)))
            inv = sum(p["amt"] for p in op)
            for t in td.itertuples():
                nr = sum(1 for p in op if p["rid"] == t.rid); w = eq * t.pct / 100
                if nr >= t.mx or inv + w > eq or any(p["tk"] == t.ticker for p in op): continue
                op.append(dict(rid=t.rid, tk=t.ticker, buy=t.buy, exit=t.exit, low=t.low,
                               cost=t.cost, stop=t.stop, amt=w, ex=i + t.hold)); inv += w
                if t.rid == "P4": n4 += 1
        curve.append(eq)
    C = pd.Series(curve); dd = (C / C.cummax() - 1) * 100
    return dict(nav=C.iloc[-1], mdd=dd.min(), n4=n4)

CAND = [("현재 -20/-10/-40", -20, -10, -40), ("낙폭 -30", -20, -10, -30), ("낙폭 -25", -20, -10, -25),
        ("업종 -15", -15, -10, -40), ("조합 -15/-10/-30", -15, -10, -30), ("조합 -12/-8/-25", -12, -8, -25)]
PERIODS = [("전체 2018~26","20180101","20991231"), ("학습 2018~22","20180101","20221231"),
           ("검증 2023~26","20230101","20991231"), ("붐제외 ~2024","20180101","20241231")]
SEEDS = 12
SETS = {nm: build({**RULES, "P4": (KP, 5, 0.15, 3, 4, cond_of(u, dm, md))}) for nm, u, dm, md in CAND}
print(f"  계좌 수익금 비교 (시드 {SEEDS}회 · 같은 시드끼리 짝지어 · 자산 배수)\n")
print(f"  {'조건':<18}" + "".join(f"{p[0]:>16}" for p in PERIODS) + f"{'낙폭':>8}{'P4체결':>8}")
BASEL = None
for nm, u, dm, md in CAND:
    S = SETS[nm]; cells = []; ref = []
    for _, d0, d1 in PERIODS:
        ds = [d for d in adates if d0 <= d <= d1]
        rs = [sim(S, ds, seed=k) for k in range(SEEDS)]
        ref.append([r["nav"] for r in rs])
    last = [sim(S, [d for d in adates if d >= "20180101"], seed=k) for k in range(SEEDS)]
    if BASEL is None: BASEL = ref
    line = ""
    for i, col in enumerate(ref):
        m = np.median(col)
        w = np.mean([a > b for a, b in zip(col, BASEL[i])]) * 100
        line += f"{m:>10.2f}배({w:>3.0f}%)" if nm != CAND[0][0] else f"{m:>10.2f}배      "
    print(f"  {nm:<18}{line}{np.median([r['mdd'] for r in last]):>7.1f}%{np.median([r['n4'] for r in last]):>8.0f}")
print("\n  ※ 괄호는 같은 시드에서 현재 조건을 이긴 비율. 50% 근처면 우열이 없다는 뜻이다.")
