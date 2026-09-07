# -*- coding: utf-8 -*-
"""트레일링 스톱 검토 — 손절이 있는 세 규칙의 고정 손절을 트레일링으로 바꿔 본다.

단서(2026-09-07 유튜브 스윙 실측): 같은 신호에 고정 손절을 걸면 초과 +0.62·검증 CI -0.7 인데
트레일링 -3% 는 초과 +1.19·검증 CI +0.4 였다. 다만 그건 유튜브 신호(지지선 바운스)에 붙인 값이라
우리 규칙에 그대로 옮겨지지 않는다. 손절을 쓰는 세 규칙에 직접 붙여 다시 잰다.
  [조용한 신고가] 40일·손절 -15% / [업종붕괴 이탈] 5일·손절 -15% / [깊은 이격] 5일·손절 -10%

트레일링 정의: 보유 중 종가 최고점(시작값은 매수가) 대비 X% 하락하면 그 가격에 청산.
 ⚠ 청산가는 '발동 시점까지의 최고점' 으로만 계산한다 — 보유기간 전체 최고점을 쓰면 미래를 본다.
비교: 현행(고정 손절) / 손절 없음 / 트레일링 3·5·8·10·15%.
판정: 학습2016~22 · 검증2023~26 · 중앙값 · 월블록 CI 하한 · 최악값, 그리고 계좌 짝비교(시드 12).
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
NAME = {"P1":"조용한 신고가","P4":"업종붕괴 이탈","P6":"깊은 이격"}

def rets(K, hold, stop=None, trail=None):
    """거래별 수익률. stop=고정손절(저가 기준), trail=트레일링(종가 기준)"""
    g = K.groupby("ticker", sort=False)
    if trail:
        C = np.column_stack([g.close.shift(-i).values for i in range(1, hold+1)])
        run = np.maximum.accumulate(np.column_stack([K.buy.values, C]), axis=1)[:, 1:]
        hit = C <= run*(1-trail)
        ok = hit.any(axis=1); first = np.where(ok, hit.argmax(axis=1), 0)
        px = np.where(ok, run[np.arange(len(C)), first]*(1-trail), C[:, -1])
        r = (px/K.buy.values-1)*100 - K.cost.values
        return np.where(np.isnan(C).all(axis=1), np.nan, r), ok
    if stop:
        low = pd.concat([g.low.shift(-i) for i in range(hold)], axis=1).min(axis=1)
        hit = (low <= K.buy*(1-stop)).fillna(False)
        return np.where(hit, -stop*100 - K.cost, K[f"n{hold}"]), hit.values
    return K[f"n{hold}"].values, np.zeros(len(K), bool)

def take(K, cond, hold, r):
    m = cond.fillna(False); X = K[m].copy(); X["_r"] = r[m.values]; X = X.dropna(subset=["_r"])
    di = {x:i for i,x in enumerate(sorted(K.date.unique()))}
    X["di"] = X.date.map(di); X = X.sort_values("di"); keep, last = [], {}
    for t,i,ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t,-10**9) >= i: continue
        last[t] = i+hold; keep.append(ix)
    return X.loc[keep]
def ci(z, n=1200, seed=0):
    if len(z) < 8: return float("nan")
    rng = np.random.default_rng(seed); mo = z.date.str[:6].values
    g = [z._r.values[mo == m] for m in np.unique(mo)]; k = len(g)
    return np.percentile([np.concatenate([g[i] for i in rng.integers(0,k,k)]).mean() for _ in range(n)], 5)
def cell(z):
    return (f"{len(z):>4}건{z._r.mean():>+7.2f}%{z._r.median():>+6.1f}{(z._r>0).mean()*100:>4.0f}%{ci(z):>+6.1f}"
            if len(z) >= 8 else f"{'—':>27}")
print("① 규칙 단위 (2016~)")
for rid in ("P1","P4","P6"):
    K, hold, stop, pct, mx, cond = RULES[rid]
    print(f"\n [{NAME[rid]}] {hold}일 보유 · 현행 손절 -{stop*100:.0f}%")
    print(f"  {'방식':<16}{'학습2016~22':>27}{'검증2023~26':>27}{'기준2016~':>27}{'최악':>8}{'발동률':>7}")
    for lab, kw in ([("현행 손절", dict(stop=stop)), ("손절 없음", {})] +
                    [(f"트레일링 -{t*100:.0f}%", dict(trail=t)) for t in (0.03,0.05,0.08,0.10,0.15)]):
        r, fired = rets(K, hold, **kw)
        Z = take(K, cond, hold, r); Z = Z[Z.date >= "20160101"]
        if len(Z) < 8: print(f"  {lab:<16} 표본 부족"); continue
        a = Z[Z.date <= "20221231"]; b = Z[Z.date >= "20230101"]
        fr = fired[Z.index].mean()*100
        print(f"  {lab:<16}{cell(a):>27}{cell(b):>27}{cell(Z):>27}{Z._r.min():>+7.1f}%{fr:>6.0f}%")
