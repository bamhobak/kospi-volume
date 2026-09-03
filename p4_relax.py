# -*- coding: utf-8 -*-
"""[업종붕괴 이탈] 조건 완화 — 2020년 3월 한 사건 쏠림을 줄인다.

현재 조건은 업종 -20% · 20일선 이격 -10% · 60일 최대낙폭 -40% 를 동시에 요구한다.
셋 다 극단이라 대폭락 때만 동시에 성립하고, 그 결과 2020년 신호 1,640건 중 1,627건이
3월에 몰렸다(실거래 775건의 절반). 연도 쏠림이 아니라 '한 사건 쏠림' 이다.

문턱을 늦추면 신호가 늘고 흩어진다. 다만 성적이 같이 나빠지면 의미가 없다.
그래서 가장 중요한 잣대를 하나 둔다 — **2020년 3월을 통째로 빼고도 버는가.**
그 사건이 성적을 만든 것이라면 빼는 순간 무너질 것이다.

사용: python p4_relax.py
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
KP, RULES = ns["KP"], ns["RULES"]
base, dn60 = ns["base"], ns["dn60"]
HOLD, STOP = 5, 0.15

g = KP.groupby("ticker", sort=False)
_lo = pd.concat([g.low.shift(-i) for i in range(HOLD)], axis=1).min(axis=1)
KP["_r"] = np.where((_lo <= KP.buy * (1 - STOP)).fillna(False), -STOP * 100 - KP.cost, KP.n5)
del _lo; gc.collect()
d = sorted(KP.date.unique()); DI = {x: i for i, x in enumerate(d)}
KP["di"] = KP.date.map(DI)

def trades(cond):
    X = KP[cond.fillna(False)].dropna(subset=["_r"]).sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i + HOLD; keep.append(ix)
    return X.loc[keep]

def boot(v, k, seed=127, n=1500):
    if len(v) < 20: return None
    rng = np.random.default_rng(seed); D = pd.DataFrame({"r": v, "ym": k})
    by = {m: x.r.to_numpy() for m, x in D.groupby("ym")}; ms = list(by)
    if len(ms) < 3: return None
    return np.percentile([np.concatenate([by[x] for x in rng.choice(ms, len(ms), replace=True)]).mean()
                          for _ in range(n)], [2.5, 97.5])
trim = lambda v: v[v <= np.percentile(v, 95)].mean() if len(v) >= 20 else np.nan

# 현재: base(KP,10) & dn60 & u<=-20 & dma20<=-10 & mdd60<=-40 & srd & close>=1000
CORE = base(KP, 10) & dn60(KP) & (KP.srd == True) & (KP.close >= 1000)
def cond_of(u, dma, mdd): return CORE & (KP.u <= u) & (KP.dma20 <= dma) & (KP.mdd60 <= mdd)

def row(nm, Z):
    if len(Z) < 30: print(f"  {nm:<26} {len(Z):>5} (표본 부족)"); return None
    v = Z._r.to_numpy()
    ym = Z.date.str[:6]
    top_m = ym.value_counts().max() / len(Z) * 100          # 최다 '월' 비중 ← 사건 쏠림
    top_y = Z.date.str[:4].value_counts().max() / len(Z) * 100
    ex = Z[~Z.date.str.startswith("202003")]                # 2020년 3월 제외
    zi = Z[Z.date < "20230101"]
    ci = boot(zi._r.values, zi.date.str[:6])
    exci = boot(ex[ex.date < "20230101"]._r.values, ex[ex.date < "20230101"].date.str[:6])
    f = f"[{ci[0]:+.1f},{ci[1]:+.1f}]" if ci is not None else "-"
    g2 = f"[{exci[0]:+.1f},{exci[1]:+.1f}]" if exci is not None else "-"
    print(f"  {nm:<26} {len(Z):>5} {v.mean():>+6.2f}% {(v>0).mean()*100:>4.0f}% {np.median(v):>+6.2f}% "
          f"{trim(v):>+6.2f}% {top_m:>5.0f}% {top_y:>5.0f}% {f:>13} │ "
          f"{len(ex):>5} {ex._r.mean():>+6.2f}% {np.median(ex._r):>+6.2f}% {g2:>13}")
    return dict(n=len(Z), avg=v.mean(), med=np.median(v), trim=trim(v), top_m=top_m, top_y=top_y,
                ci=ci, ex_n=len(ex), ex_avg=ex._r.mean(), ex_med=np.median(ex._r), ex_ci=exci)

print("  전체 성적                                                              │ 2020년 3월 제외")
print(f"  {'조건 (업종/이격/낙폭)':<26} {'건수':>5} {'평균':>7} {'승률':>5} {'중앙':>7} {'절삭':>7} "
      f"{'최다월':>6} {'최다年':>6} {'학습CI':>13} │ {'건수':>5} {'평균':>7} {'중앙':>7} {'학습CI':>13}")
R = {}
R["현재 -20/-10/-40"] = row("현재 -20/-10/-40 ★", trades(cond_of(-20, -10, -40)))
print()
for mdd in (-35, -30, -25, -20):
    R[f"낙폭 {mdd}"] = row(f"낙폭만 완화 {mdd}", trades(cond_of(-20, -10, mdd)))
print()
for u in (-15, -12, -10, -5):
    R[f"업종 {u}"] = row(f"업종만 완화 {u}", trades(cond_of(u, -10, -40)))
print()
for dma in (-8, -6, -4):
    R[f"이격 {dma}"] = row(f"이격만 완화 {dma}", trades(cond_of(-20, dma, -40)))
print()
for u, dma, mdd in ((-15, -8, -30), (-15, -10, -30), (-12, -8, -25), (-10, -6, -25), (-15, -6, -20)):
    R[f"{u}/{dma}/{mdd}"] = row(f"조합 {u}/{dma}/{mdd}", trades(cond_of(u, dma, mdd)))

print("\n  ── 판정: 2020년 3월을 빼고도 버는가 (학습CI 하한>0 · 중앙>0) ──")
for nm, r in R.items():
    if not r: continue
    ok = r["ex_ci"] is not None and r["ex_ci"][0] > 0 and r["ex_med"] > 0
    print(f"    {'✅' if ok else '❌'} {nm:<20} 3월제외 {r['ex_n']:>4}건 {r['ex_avg']:>+6.2f}% "
          f"(중앙 {r['ex_med']:>+5.2f}%) · 최다월 {r['top_m']:>4.0f}%")
