# -*- coding: utf-8 -*-
"""트레일링 스톱 계좌 검증 — 자리 회전까지 반영해 판정한다.

규칙 단위(trail_test.py)에서 트레일링이 고정 손절보다 나았다:
  [업종붕괴 이탈] +5.58%→+8.13%(-3%) · [깊은 이격] +5.45%→+9.17%(-3%) · [조용한 신고가] +6.95%→+7.24%(-8%)
그런데 계좌에서는 두 힘이 겹친다 — ① 트레일링으로 일찍 팔면 자리가 빨리 비어 다음 신호를 더 잡는다(유리)
② 일찍 팔아 남은 상승을 놓친다(불리). 어느 쪽이 큰지는 계좌로만 알 수 있다.
그래서 신호마다 '실제 청산일' 과 '확정 수익률' 을 미리 계산해 넣고, 그 값으로 계좌를 굴린다.
⚠ 일봉 종가로 재는 트레일링은 실전보다 유리하다(장중 발동을 못 본다). 좁은 문턱(-3%)일수록 심하다.
   그래서 좁은 값이 좋게 나와도 곧바로 채택하지 않고, 넓은 문턱에서도 개선이 있는지 함께 본다.
"""
import io, os, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent; SEEDS = 12
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES = ns["KP"], ns["KQ"], ns["RULES"]
adates = sorted(set(KP.date) | set(KQ.date)); ADI = {d: i for i, d in enumerate(adates)}
TRAIL = {"P1": None, "P4": None, "P6": None}      # 규칙별 트레일링 폭(None=현행 고정손절)

def build2(trail):
    """신호표. 트레일링을 쓰는 규칙은 청산일(held)과 수익률(ret)을 미리 확정한다."""
    sig = []
    for rid, (K, hold, stop, pct, mx, cond) in RULES.items():
        g = K.groupby("ticker", sort=False)
        X = K[cond.fillna(False)].copy()
        X["rid"], X["pct"], X["mx"] = rid, pct, mx
        t = trail.get(rid)
        if t:
            C = np.column_stack([g.close.shift(-i).values for i in range(1, hold+1)])
            run = np.maximum.accumulate(np.column_stack([K.buy.values, C]), axis=1)[:, 1:]
            hit = C <= run*(1-t)
            ok = hit.any(axis=1); first = np.where(ok, hit.argmax(axis=1), hold-1)
            px = np.where(ok, run[np.arange(len(C)), first]*(1-t), C[:, -1])
            r = (px/K.buy.values-1)*100 - K.cost.values
            r = np.where(np.isnan(C).all(axis=1), np.nan, r)
            X["ret"] = r[cond.fillna(False).values]
            X["held"] = (first + 1)[cond.fillna(False).values]      # 실제 보유 거래일
        else:
            low = pd.concat([g.low.shift(-i) for i in range(hold)], axis=1).min(axis=1)
            h2 = (low <= K.buy*(1-stop)).fillna(False) if stop else pd.Series(False, index=K.index)
            r = np.where(h2, -(stop or 0)*100 - K.cost, K[f"n{hold}"])
            X["ret"] = r[cond.fillna(False).values]; X["held"] = hold
        sig.append(X[["date","ticker","rid","pct","mx","ret","held"]])
    S = pd.concat(sig).dropna(subset=["ret"]).copy()
    S["di"] = S.date.map(ADI)
    return S.sort_values(["di","rid"]).reset_index(drop=True)

def sim(S, ds, seed):
    eq = 1.0; op = []; curve = []
    lo_i, hi_i = ADI[ds[0]], ADI[ds[-1]]
    byd = {i: g for i, g in S[(S.di >= lo_i) & (S.di <= hi_i)].groupby("di")}
    rng = np.random.default_rng(seed)
    for d in ds:
        i = ADI[d]; st = []
        for p in op:
            if p["ex"] <= i: eq += p["amt"]*p["ret"]/100
            else: st.append(p)
        op = st; td = byd.get(i)
        if td is not None:
            td = td.sample(frac=1, random_state=int(rng.integers(1 << 31)))
            inv = sum(p["amt"] for p in op)
            for t in td.itertuples():
                nr = sum(1 for p in op if p["rid"] == t.rid); w = eq*t.pct/100
                if nr >= t.mx or inv+w > eq or any(p["tk"] == t.ticker for p in op): continue
                op.append(dict(rid=t.rid, tk=t.ticker, ret=t.ret, amt=w, ex=i+int(t.held))); inv += w
        curve.append(eq)
    Cv = pd.Series(curve); dd = (Cv/Cv.cummax()-1)*100
    return Cv.iloc[-1], dd.min()

PER = [("학습 2016~22","20160101","20221231"), ("검증 2023~26","20230101","20991231"),
       ("기준 2016~","20160101","20991231")]
VAR = [("현행(고정 손절)", {}),
       ("업종붕괴만 트레일 -10%", {"P4":0.10}), ("깊은이격만 트레일 -10%", {"P6":0.10}),
       ("조용한신고가만 트레일 -8%", {"P1":0.08}),
       ("셋 다 -10%", {"P1":0.10,"P4":0.10,"P6":0.10}),
       ("셋 다 -8%", {"P1":0.08,"P4":0.08,"P6":0.08}),
       ("셋 다 -5%", {"P1":0.05,"P4":0.05,"P6":0.05}),
       ("셋 다 -3%", {"P1":0.03,"P4":0.03,"P6":0.03})]
print(f"  {'안':<24}" + "".join(f"{p[0]:>26}" for p in PER))
print(f"  {'':<24}" + "".join(f"{'자산':>10}{'낙폭':>8}{'시드승':>8}" for p in PER))
print("  " + "-"*102)
BASE_N = {}
for nm, tr in VAR:
    S = build2(tr); row = ""
    for pn, lo, hi in PER:
        ds = [d for d in adates if lo <= d <= hi]
        R = [sim(S, ds, k) for k in range(SEEDS)]
        nav = [x[0] for x in R]; mdd = np.median([x[1] for x in R])
        if not tr: BASE_N[pn] = nav; w = "기준"
        else: w = f"{sum(a>b for a,b in zip(nav, BASE_N[pn]))}/{SEEDS}"
        row += f"{np.median(nav):>9.2f}배{mdd:>7.0f}%{w:>8}"
    print(f"  {nm:<24}{row}")

# ── 연도별 — 사용자 기준(가장 최근 해에 지면 채택 불가) 확인
print("\n연도별 계좌 수익률 (중앙값)")
def sim_curve(S, ds, seed):
    eq=1.0; op=[]; curve=[]
    lo_i, hi_i = ADI[ds[0]], ADI[ds[-1]]
    byd = {i: g for i, g in S[(S.di>=lo_i)&(S.di<=hi_i)].groupby("di")}
    rng = np.random.default_rng(seed)
    for d in ds:
        i = ADI[d]; st=[]
        for p in op:
            if p["ex"] <= i: eq += p["amt"]*p["ret"]/100
            else: st.append(p)
        op = st; td = byd.get(i)
        if td is not None:
            td = td.sample(frac=1, random_state=int(rng.integers(1<<31)))
            inv = sum(p["amt"] for p in op)
            for t in td.itertuples():
                nr = sum(1 for p in op if p["rid"]==t.rid); w = eq*t.pct/100
                if nr>=t.mx or inv+w>eq or any(p["tk"]==t.ticker for p in op): continue
                op.append(dict(rid=t.rid, tk=t.ticker, ret=t.ret, amt=w, ex=i+int(t.held))); inv+=w
        curve.append(eq)
    return pd.Series(curve)
ds = [d for d in adates if d >= "20160101"]
yrs = np.array([d[:4] for d in ds])
CUR = {}
for nm, tr in (("현행", {}), ("셋 다 -8%", {"P1":0.08,"P4":0.08,"P6":0.08})):
    S = build2(tr); CUR[nm] = [sim_curve(S, ds, k) for k in range(SEEDS)]
print(f"  {'해':<6}{'현행':>10}{'셋 다 -8%':>12}{'차이':>9}")
for y in sorted(set(yrs)):
    idx = np.where(yrs == y)[0]; i0, i1 = max(idx[0]-1,0), idx[-1]
    v = {}
    for nm in CUR:
        v[nm] = np.median([(c.to_numpy()[i1]/c.to_numpy()[i0]-1)*100 for c in CUR[nm]])
    print(f"  {y:<6}{v['현행']:>+9.1f}%{v['셋 다 -8%']:>+11.1f}%{v['셋 다 -8%']-v['현행']:>+8.1f}")

# ── 실행 부담: 트레일링이 며칠 만에 발동하나
print("\n트레일링 -8% 발동 시점 분포 (규칙별)")
S = build2({"P1":0.08,"P4":0.08,"P6":0.08})
for rid, nm in (("P1","조용한 신고가"), ("P4","업종붕괴 이탈"), ("P6","깊은 이격")):
    z = S[(S.rid==rid) & (S.date>="20160101")]
    full = RULES[rid][1]
    early = (z.held < full).mean()*100
    print(f"  {nm:<12} 최대 {full}일 · 평균 보유 {z.held.mean():.1f}일 · 조기청산 {early:.0f}% · 중앙 {z.held.median():.0f}일")
