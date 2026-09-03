# -*- coding: utf-8 -*-
"""[업종붕괴 이탈] 조이기 재검토 — 이번엔 수익금까지 본다.

지난번([폭락반등] 신용잔고)에서 배운 것: 조일수록 규칙 평균수익률은 오르지만
신호가 줄어 실제 수익금은 어느 지점에서 꺾인다. 평균만 보고 문턱을 고르면 틀린다.
그래서 후보마다 세 가지를 함께 잰다.
  1) 규칙 단위 성적 (게이트 통과 여부)
  2) 9규칙 계좌 수익금 — 다른 규칙과 자리를 다투므로 여기서 뒤집힐 수 있다
  3) 이 규칙 단독·자금 전액 수익금 — 규칙 자체의 힘

현재 [업종붕괴 이탈]: 거래대금 10억↑ · 하락장 · 업종60일 ≤-20% · 20일선이격 ≤-10%
                     · 60일최대낙폭 ≤-40% · 공매도감소 · 5일 보유 · 손절 -15%
규율: 조건은 학습(2018~22)만 보고 고르고 검증(2023~)은 확인용.
"""
import io, sys, gc
from pathlib import Path
import numpy as np, pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
src = (BASE / "portfolio.py").read_text(encoding="utf-8")
ns = {"__file__": str(BASE / "portfolio.py")}
class _Sink(io.TextIOWrapper):
    def write(self, *a, **k): return 0
real = sys.stdout; sys.stdout = _Sink(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES = ns["KP"], ns["KQ"], ns["RULES"]
base, dn60 = ns["base"], ns["dn60"]
HOLD, STOP = 5, 0.15
CORE = RULES["P4"][5]
adates = sorted(set(KP.date) | set(KQ.date)); ADI = {d: i for i, d in enumerate(adates)}
kdates = sorted(KP.date.unique()); KDI = {d: i for i, d in enumerate(kdates)}
KP["di"] = KP.date.map(KDI); KP["yr"] = KP.date.str[:4]

# 5일 보유·손절 -15% 를 반영한 수익
_g = KP.groupby("ticker", sort=False)
_lo = pd.concat([_g.low.shift(-i) for i in range(HOLD)], axis=1).min(axis=1)
KP["_r"] = np.where((_lo <= KP.buy * (1 - STOP)).fillna(False), -STOP*100 - KP.cost, KP.n5)
KP["_exit"] = _g.close.shift(-HOLD)
KP["_low"] = _g.low.shift(-1).rolling(HOLD, min_periods=1).min().shift(-(HOLD-1))
del _lo; gc.collect()

def boot(v, k, seed=127, n=2000):
    if len(v) < 20: return None
    rng = np.random.default_rng(seed); d = pd.DataFrame({"r": v, "ym": k})
    by = {m: g.r.to_numpy() for m, g in d.groupby("ym")}; ms = list(by)
    if len(ms) < 3: return None
    return np.percentile([np.concatenate([by[x] for x in rng.choice(ms, len(ms), replace=True)]).mean()
                          for _ in range(n)], [2.5, 97.5])

def trades(m):
    v = m.fillna(False).values
    X = KP[v].copy()
    X = X.dropna(subset=["_r"]).sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i + HOLD; keep.append(ix)
    return X.loc[keep]

def build(R):
    sig = []
    for rid, (K, hold, stop, pct, mx, cond) in R.items():
        g = K.groupby("ticker", sort=False); ex = g.close.shift(-hold)
        lo = g.low.shift(-1).rolling(hold, min_periods=1).min().shift(-(hold-1))
        X = K[cond.fillna(False)].copy()
        X["rid"] = rid; X["hold"] = hold; X["stop"] = stop if stop else np.nan
        X["pct"] = pct; X["mx"] = mx
        X["exit"] = ex.reindex(X.index); X["low"] = lo.reindex(X.index)
        sig.append(X[["date","ticker","rid","hold","stop","pct","mx","buy","exit","low","cost"]])
    S = pd.concat(sig).dropna(subset=["buy","exit","cost"]); S = S[S.buy > 0].copy()
    S["di"] = S.date.map(ADI); return S.sort_values(["di","rid"]).reset_index(drop=True)

def sim(S, ds):
    eq = 1.0; op = []; curve = []; by = {i: g for i, g in S.groupby("di")}
    for i, d in enumerate(ds):
        st = []
        for p in op:
            if p["ex"] <= i:
                hit = (p["stop"] == p["stop"]) and (p["low"]/p["buy"]-1)*100 <= -p["stop"]*100
                r = (-p["stop"]*100 - p["cost"]) if hit else ((p["exit"]/p["buy"]-1)*100 - p["cost"])
                eq += p["amt"]*r/100
            else: st.append(p)
        op = st; td = by.get(i)
        if td is not None:
            inv = sum(p["amt"] for p in op)
            for t in td.itertuples():
                nr = sum(1 for p in op if p["rid"] == t.rid); w = eq*t.pct/100
                if nr >= t.mx or inv + w > eq or any(p["tk"] == t.ticker for p in op): continue
                op.append(dict(rid=t.rid, tk=t.ticker, buy=t.buy, exit=t.exit, low=t.low,
                               cost=t.cost, stop=t.stop, amt=w, ex=i+t.hold)); inv += w
        curve.append(eq)
    C = pd.Series(curve); dd = (C/C.cummax()-1)*100
    return C.iloc[-1], dd.min()

def money(cond):
    """9규칙 계좌 수익금 · 이 규칙 단독(자금 전액 33%×3) 수익금"""
    R = dict(RULES); K_, h, s_, p_, m_, _ = RULES["P4"]
    R["P4"] = (KP, h, s_, p_, m_, cond)
    a_nav, a_mdd = sim(build(R), adates)
    s_nav, s_mdd = sim(build({"P4": (KP, h, s_, 33, 3, cond)}), kdates)
    return a_nav-1, a_mdd, s_nav-1, s_mdd

CAND = {
 "현재(조이기 없음)": None,
 # 기존 문턱
 "업종 u≤-25": KP.u <= -25,
 "업종 u≤-30": KP.u <= -30,
 "이격 dma20≤-15": KP.dma20 <= -15,
 "이격 dma20≤-20": KP.dma20 <= -20,
 "낙폭 mdd60≤-50": KP.mdd60 <= -50,
 "낙폭 mdd60≤-55": KP.mdd60 <= -55,
 "거래대금 ≥30억": KP.amt20 >= 30,
 "거래대금 ≥100억": KP.amt20 >= 100,
 # 신용잔고 (이번에 확보한 축)
 "신용 20일 ≤0%": KP.cr_chg20 <= 0,
 "신용 20일 ≤-10%": KP.cr_chg20 <= -10,
 "신용 20일 ≤-15%": KP.cr_chg20 <= -15,
 # 수급
 "외인 fw60≥0": KP.fw60 >= 0,
 "외인 fw60≥1": KP.fw60 >= 1,
 "기관 ow20≥0": KP.ow20 >= 0,
 # 규모·기타
 "시총 ≥3천억": KP["cap조"] >= 0.3,
 "시총 ≥1조": KP["cap조"] >= 1,
 "종가위치 clv≥0.3": KP.clv >= 0.3,
 "거래량 su1≥1.5": KP.su1 >= 1.5,
 "변동성 vol20≤4": KP.vol20 <= 4,
}
print(f"  {'조건':<20} {'거래':>5} {'평균':>7} {'승률':>5} {'중앙':>7} {'IS':>7} {'OS':>7} {'최다年':>5} "
      f"{'학습CI':>13} {'계좌수익금':>10} {'계좌낙폭':>8} {'단독수익금':>10} {'단독낙폭':>8}")
rows = []
for nm, c in CAND.items():
    cond = CORE if c is None else (CORE & c)
    Z = trades(cond)
    if len(Z) < 40: print(f"  {nm:<20} {len(Z):>5} (부족)"); continue
    zi, zo = Z[Z.date < "20230101"], Z[Z.date >= "20230101"]
    ci = boot(zi._r.values, zi.date.str[:6])
    top = Z.groupby("yr")._r.size().max()/len(Z)*100
    a_p, a_m, s_p, s_m = money(cond)
    f = f"[{ci[0]:+.1f},{ci[1]:+.1f}]" if ci is not None else "-"
    print(f"  {nm:<20} {len(Z):>5} {Z._r.mean():>+6.2f}% {(Z._r>0).mean()*100:>4.0f}% "
          f"{np.median(Z._r):>+6.2f}% {zi._r.mean():>+6.2f}% {zo._r.mean():>+6.2f}% {top:>4.0f}% {f:>13} "
          f"{a_p:>8.3f}억 {a_m:>7.1f}% {s_p:>8.3f}억 {s_m:>7.1f}%")
    rows.append((nm, a_p, s_p, Z._r.mean(), top))
print("\n  계좌 수익금 상위")
for nm, a, s, r, t in sorted(rows, key=lambda x: -x[1])[:6]:
    print(f"    {nm:<20} 계좌 {a:.3f}억 · 단독 {s:.3f}억 · 규칙평균 {r:+.2f}% · 최다연도 {t:.0f}%")
print("\n※ 규칙 평균만 높고 수익금이 낮으면 '신호를 잘라서 평균을 올린 것' 이다.")
