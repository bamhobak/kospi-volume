# -*- coding: utf-8 -*-
"""[외인 매집] 추가매수 — 청산 방식 세 가지 비교.

  A 따로 청산    최초분은 최초일+60, 추가분은 추가일+60 (지금 구현된 방식)
  B 첫 거래일 기준 둘 다 최초일+60 — 추가분의 보유기간을 그만큼 줄인다
  C 추가일 기준   둘 다 추가일+60 — 추가매수가 일어난 시점에 최초분 청산을 미룬다

C 가 미래를 엿보는 것 아닌가? 아니다. 최초 매수 때 정해 두는 게 아니라 추가매수가
실제로 일어난 그 시점에 최초분의 청산일을 미루는 것이라 실행 가능하다.

세 방식의 청산일이 다르므로 청산가를 미리 못 박을 수 없다. 그래서 신호 행의
패널 인덱스(ki)를 들고 다니며 청산 시점에 그때의 종가를 조회한다.

사용: python addbuy_exit.py
"""
import io, sys
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
adates = sorted(set(KP.date) | set(KQ.date)); ADI = {d: i for i, d in enumerate(adates)}

_K, _h, _s, _p, _m, P7 = RULES["P7"]
c = P7.fillna(False).to_numpy()
new_tk = KP.ticker.ne(KP.ticker.shift()).to_numpy(); idx = np.arange(len(c))
base = np.where(~c, idx, -1); base = np.where(new_tk & c, idx - 1, base)
base = np.maximum.accumulate(base)
stk = np.where(c, idx - base, 0)
_fb = pd.Series(np.where(stk == 1, KP.buy.to_numpy(), np.nan), index=KP.index)
first_buy = _fb.groupby([KP.ticker, pd.Series(base, index=KP.index)]).transform("first")
win = (KP.close / first_buy - 1) * 100
ADD = pd.Series(c & (stk >= 2) & (win.fillna(-1).to_numpy() > 0), index=KP.index)

# 청산가를 그때그때 조회하기 위한 배열 (KP 는 ticker,date 정렬이라 행 이동 = 거래일 이동)
CLOSE = KP.close.to_numpy(); TKA = KP.ticker.to_numpy(); NKP = len(KP)
LASTI = pd.Series(idx, index=KP.index).groupby(KP.ticker).transform("max").to_numpy()
def exit_px(ki, h):
    """ki 행에서 h 거래일 뒤 종가. 종목 데이터가 끝나면 마지막 종가로 청산한다."""
    j = min(ki + h, LASTI[ki])
    return CLOSE[j]

def build(R, add_stk=False):
    sig = []
    for rid, (K, hold, stop, pct, mx, cond) in R.items():
        g = K.groupby("ticker", sort=False); ex = g.close.shift(-hold)
        lo = g.low.shift(-1).rolling(hold, min_periods=1).min().shift(-(hold - 1))
        X = K[cond.fillna(False)].copy()
        X["rid"] = rid; X["hold"] = hold; X["stop"] = stop if stop else np.nan
        X["pct"] = pct; X["mx"] = mx
        X["exit"] = ex.reindex(X.index); X["low"] = lo.reindex(X.index)
        X["ki"] = X.index if K is KP else -1          # 동적 청산은 [외인 매집] 에만 쓴다
        X["stk"] = stk[X.index] if (K is KP) else 0
        sig.append(X[["date","ticker","rid","hold","stop","pct","mx","buy","exit","low","cost","ki","stk"]])
    S = pd.concat(sig).dropna(subset=["buy","cost"]); S = S[S.buy > 0].copy()
    S["di"] = S.date.map(ADI); return S.sort_values(["di","rid"]).reset_index(drop=True)

def sim(S, ds, mode, seed=None):
    eq = 1.0; op = []; curve = []; wins = []
    lo_i, hi_i = ADI[ds[0]], ADI[ds[-1]]
    by = {i: g for i, g in S[(S.di >= lo_i) & (S.di <= hi_i)].groupby("di")}
    rng = np.random.default_rng(seed) if seed is not None else None
    for d in ds:
        i = ADI[d]; st = []
        for p in op:
            if p["ex"] <= i:
                px = p["exit"] if p["exit"] == p["exit"] else None
                if p["dyn"]: px = exit_px(p["ki"], p["h"])
                if px is None: st.append(p); continue
                hit = (p["stop"] == p["stop"]) and (p["low"] / p["buy"] - 1) * 100 <= -p["stop"] * 100
                r = (-p["stop"] * 100 - p["cost"]) if hit else ((px / p["buy"] - 1) * 100 - p["cost"])
                eq += p["amt"] * r / 100; wins.append(r > 0)
            else: st.append(p)
        op = st; td = by.get(i)
        if td is not None:
            if rng is not None: td = td.sample(frac=1, random_state=int(rng.integers(1 << 31)))
            inv = sum(p["amt"] for p in op)
            for t in td.itertuples():
                nr = sum(1 for p in op if p["rid"] == t.rid); w = eq * t.pct / 100
                if nr >= t.mx or inv + w > eq: continue
                h = t.hold
                if t.rid == "P7add":
                    bp = [p for p in op if p["tk"] == t.ticker and p["rid"] == "P7"]
                    if not bp: continue
                    if any(p["tk"] == t.ticker and p["rid"] == "P7add" for p in op): continue
                    if mode == "B":                       # 최초분과 같은 날 청산 — 남은 만큼만
                        h = 61 - int(t.stk)
                        if h < 1: continue
                    elif mode == "C":                     # 최초분을 이 매수분에 맞춰 미룬다
                        for q in bp: q["ex"] = i + h; q["h"] = q["ex"] - q["di"]; q["dyn"] = True
                elif any(p["tk"] == t.ticker for p in op): continue
                op.append(dict(rid=t.rid, tk=t.ticker, buy=t.buy, exit=t.exit, low=t.low, cost=t.cost,
                               stop=t.stop, amt=w, ex=i + h, ki=int(t.ki), h=h, di=i,
                               dyn=(t.rid in ("P7", "P7add") and t.ki >= 0))); inv += w
        curve.append(eq)
    C = pd.Series(curve); dd = (C / C.cummax() - 1) * 100
    yrs = len(ds) / 246
    return dict(nav=C.iloc[-1], cagr=(C.iloc[-1] ** (1 / yrs) - 1) * 100, mdd=dd.min(),
                win=np.mean(wins) * 100 if wins else np.nan, n=len(wins))

R_ADD = dict(RULES); R_ADD["P7add"] = (KP, 60, None, 4, 5, ADD)
SA, SB = build(RULES), build(R_ADD)
PERIODS = [("전체 2018~26", "20180101", "20991231"), ("학습 2018~22", "20180101", "20221231"),
           ("검증 2023~26", "20230101", "20991231"), ("붐 제외 ~2024", "20180101", "20241231")]
SEEDS = 15
MODES = [("A 따로 청산", "A"), ("B 첫 거래일 기준", "B"), ("C 추가일 기준", "C")]
print(f"  청산 방식 비교 (시드 {SEEDS}회 · 같은 시드끼리 짝지어 비교 · 자산은 시작 1.0 배수)\n")
for nm, d0, d1 in PERIODS:
    ds = [d for d in adates if d0 <= d <= d1]
    A0 = [sim(SA, ds, "A", seed=k) for k in range(SEEDS)]
    b0 = np.median([x["nav"] for x in A0])
    print(f"  {nm}   기준(추가매수 없음) {b0:.2f}배 · 낙폭 {np.median([x['mdd'] for x in A0]):.1f}%")
    for label, mode in MODES:
        B0 = [sim(SB, ds, mode, seed=k) for k in range(SEEDS)]
        dn = [b["nav"] - a["nav"] for a, b in zip(A0, B0)]
        print(f"    {label:<16} {np.median([x['nav'] for x in B0]):>6.2f}배 "
              f"({np.median(dn):+.2f}) · 낙폭 {np.median([x['mdd'] for x in B0]):>6.1f}% "
              f"· 승률 {np.median([x['win'] for x in B0]):>4.1f}% "
              f"· 거래 {np.median([x['n'] for x in B0]):>4.0f}건 · 이긴 시드 {np.mean([x>0 for x in dn])*100:>3.0f}%")
    print()
