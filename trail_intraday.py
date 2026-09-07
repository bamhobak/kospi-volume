# -*- coding: utf-8 -*-
"""트레일링 기준을 종가 vs 장중 고가로 비교 — 어느 쪽이 실제로 나은가.

사용자 지적(2026-09-08): 보유 종목은 장중 10분마다 시세를 받고 있으니 그 최고가를 쓰면 되지 않나.
맞는 말이고, 일봉에 high·low 가 있어 **과거로도 잴 수 있다**. 세 방식을 나란히 놓는다.
  A) 종가 기준(현행 채택본) — 보유 중 종가 최고점 대비 -N%, 종가로 판정, 다음날 시가 매도
  B) 장중 고가 기준 · 저가로 판정 — 진짜 트레일링 스톱 주문과 같다. 보유 중 고가 최고점 대비 -N% 선에
     그날 저가가 닿으면 그 가격에 체결된 것으로 본다(장중 즉시 청산).
  C) 장중 고가 기준 · 종가로 판정 — 선은 고가로 따라가되 판정만 종가로(절충).
 ⚠ 일봉으로는 그날 고가와 저가 중 무엇이 먼저였는지 모른다. B 는 '전날까지의 최고가' 로 선을 잡아
   오늘 저가와 비교한다 — 같은 날 신고가를 찍고 되밀린 경우를 과대평가하지 않기 위해서다.
"""
import io, os, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
RULES = ns["RULES"]
NAME = {"P1":"조용한 신고가","P4":"업종붕괴 이탈","P6":"깊은 이격"}

def calc(K, hold, t, mode):
    g = K.groupby("ticker", sort=False)
    C = np.column_stack([g.close.shift(-i).values for i in range(1, hold+1)])
    H = np.column_stack([g.high.shift(-i).values for i in range(1, hold+1)])
    L = np.column_stack([g.low.shift(-i).values for i in range(1, hold+1)])
    buy = K.buy.values[:, None]
    if mode == "close":                       # A) 종가로 따라가고 종가로 판정
        run = np.maximum.accumulate(np.hstack([buy, C]), axis=1)[:, 1:]
        hit = C <= run*(1-t); px_at = run*(1-t)
    elif mode == "high_low":                  # B) 고가로 따라가고 저가로 판정(장중 청산)
        run_prev = np.maximum.accumulate(np.hstack([buy, H]), axis=1)[:, :-1]   # 전날까지의 최고가
        hit = L <= run_prev*(1-t); px_at = run_prev*(1-t)
    else:                                     # C) 고가로 따라가고 종가로 판정
        run = np.maximum.accumulate(np.hstack([buy, H]), axis=1)[:, 1:]
        hit = C <= run*(1-t); px_at = run*(1-t)
    ok = hit.any(axis=1); first = np.where(ok, hit.argmax(axis=1), hold-1)
    idx = np.arange(len(C))
    px = np.where(ok, px_at[idx, first], C[:, -1])
    r = (px/K.buy.values-1)*100 - K.cost.values
    return np.where(np.isnan(C).all(axis=1), np.nan, r), ok, first+1

def take(K, cond, hold, r, held):
    m = cond.fillna(False)
    X = K[m].copy(); X["_r"] = r[m.values]; X["_h"] = held[m.values]
    X = X.dropna(subset=["_r"])
    di = {x:i for i,x in enumerate(sorted(K.date.unique()))}
    X["di"] = X.date.map(di); X = X.sort_values("di"); keep, last = [], {}
    for tk,i,ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(tk,-10**9) >= i: continue
        last[tk] = i+hold; keep.append(ix)
    return X.loc[keep]
def ci(z, n=1200, seed=0):
    if len(z) < 8: return float("nan")
    rng = np.random.default_rng(seed); mo = z.date.str[:6].values
    g = [z._r.values[mo == m] for m in np.unique(mo)]; k = len(g)
    return np.percentile([np.concatenate([g[i] for i in rng.integers(0,k,k)]).mean() for _ in range(n)], 5)
def cell(z):
    return (f"{len(z):>4}건{z._r.mean():>+7.2f}%{z._r.median():>+6.1f}{(z._r>0).mean()*100:>4.0f}%{ci(z):>+6.1f}"
            if len(z) >= 8 else f"{'—':>27}")
MODES = [("A 종가·종가판정","close"), ("B 고가·저가판정(장중)","high_low"), ("C 고가·종가판정","high_low_close")]
for rid in ("P1","P4","P6"):
    K, hold, stop, pct, mx, cond = RULES[rid]
    print(f"\n[{NAME[rid]}] {hold}일 보유 · 트레일링 -8%")
    print(f"  {'방식':<22}{'학습2016~22':>27}{'검증2023~26':>27}{'기준2016~':>27}{'최악':>8}{'발동':>6}{'평균보유':>8}")
    for lab, mode in MODES:
        r, ok, held = calc(K, hold, 0.08, mode)
        Z = take(K, cond, hold, r, held); Z = Z[Z.date >= "20160101"]
        if len(Z) < 8: print(f"  {lab:<22} 표본 부족"); continue
        a = Z[Z.date <= "20221231"]; b = Z[Z.date >= "20230101"]
        print(f"  {lab:<22}{cell(a):>27}{cell(b):>27}{cell(Z):>27}"
              f"{Z._r.min():>+7.1f}%{ok[Z.index].mean()*100:>5.0f}%{Z._h.mean():>7.1f}일")
