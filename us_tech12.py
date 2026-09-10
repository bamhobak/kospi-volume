# -*- coding: utf-8 -*-
"""60일 보유 격자 — 120%↑ 는 뾰족한 봉우리인가 넓은 고원인가.

us_tech11.py 에서 60일 보유로 옮기니 1년 120%↑ 만 다중검정 3/4 를 통과하고
양옆(100·150)이 확 나빠졌다. 40일에서는 21칸이 전부 양수였는데 이상하다.
**한 칸만 좋으면 노이즈다**([[community-techniques]] 50일선 교훈) — 전면 격자로 확인한다.

  ① 60일 격자 — 상승폭 8단계 × 잔잔함 6단계, 초과와 CI 를 함께
  ② 같은 격자를 40일·20일로 — 보유기간이 바뀌면 봉우리가 움직이는가
  ③ 40일 vs 60일 짝비교 — 같은 조건에서 어느 쪽이 나은지 일관적인가
  ④ 봉우리의 정체 — 120 근처에서 무엇이 달라지나(건수·월수·월변동)

    python us_tech12.py
"""
import sys, math, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
from vp_lib import boot_ci

BASE = Path(__file__).parent
def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)

log("us_scan.pkl 읽는 중")
K = pd.read_pickle(BASE / "data/us_scan.pkl")
K = K[((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
ud = sorted(K.date.unique()); K["di"] = K.date.map({d: i for i, d in enumerate(ud)}).astype(np.int32)
UNI = (K.groupby("date").amt20.rank(pct=True) >= 0.6).fillna(False)
TK = K.ticker
K["r1"] = K.groupby(TK, sort=False).close.pct_change() * 100
K["q"] = K.groupby(TK, sort=False).r1.transform(lambda s: s.abs().rolling(60).mean())
K["multi"] = (K.ret60 > 0) & (K.ret120 > 0) & (K.ret250 > 0)
BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in (20, 40, 60)}
log(f"준비 완료 · {len(K):,}행")

def dd(cond, h, lo="20050101"):
    X = K[(cond & UNI).fillna(False)].dropna(subset=[f"n{h}"])
    X = X[X.date >= lo].sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i + h; keep.append(ix)
    d = X.loc[keep].copy()
    d["r"] = d[f"n{h}"].astype(float); d["ex"] = d.r - d.date.map(BEN[h]); d["ym"] = d.date.str[:6]
    return d[d.r.notna()]

def C(rt, ab): return K.multi & (K.ret250 >= rt) & (K.q <= ab)
UPS = (60, 80, 100, 120, 140, 160, 200, 250)
ABS = (1.0, 1.2, 1.5, 1.8, 2.0, 2.5)
W = 128

def grid(h, what):
    print(f"  {'':>10}" + "".join(f"{'잔잔≤'+str(a):>11}" for a in ABS))
    for rt in UPS:
        row = f"  1년{rt:>4}%↑"
        for ab in ABS:
            d = dd(C(rt, ab), h)
            if len(d) < 60: row += f"{'-':>11}"; continue
            if what == "ex": row += f"{d.ex.mean():>+11.2f}"
            elif what == "ci": row += f"{boot_ci(d.groupby('ym').ex.mean()):>+11.2f}"
            elif what == "t":
                r = d.groupby("ym").ex.mean().dropna()
                row += f"{r.mean()/(r.std(ddof=1)/math.sqrt(len(r))):>11.2f}"
            else: row += f"{len(d):>11,}"
        print(row)

for h in (60, 40, 20):
    print("\n" + "=" * W)
    print(f"① {h}일 보유 격자 — 초과(%p) · 2005~ 전구간")
    print("=" * W); grid(h, "ex")
    print(f"\n  ── 같은 격자의 월블록 CI 하한 (보정 전 90%) ──")
    grid(h, "ci")

print("\n" + "=" * W)
print("② 40일 vs 60일 짝비교 — 같은 조건에서 60일이 일관되게 나은가")
print("=" * W)
print(f"  {'조건':<22}{'40일 초과':>10}{'60일 초과':>10}{'차이':>9}{'40일 CI':>9}{'60일 CI':>9}{'40일 t':>8}{'60일 t':>8}")
win = 0; tot = 0
for rt in UPS:
    for ab in (1.2, 1.5, 2.0):
        d4, d6 = dd(C(rt, ab), 40), dd(C(rt, ab), 60)
        if len(d4) < 60 or len(d6) < 60: continue
        r4 = d4.groupby("ym").ex.mean().dropna(); r6 = d6.groupby("ym").ex.mean().dropna()
        t4 = r4.mean() / (r4.std(ddof=1) / math.sqrt(len(r4)))
        t6 = r6.mean() / (r6.std(ddof=1) / math.sqrt(len(r6)))
        tot += 1; win += (d6.ex.mean() > d4.ex.mean())
        print(f"  1년{rt:>4}%↑ · 잔잔≤{ab:<4}{d4.ex.mean():>+10.2f}{d6.ex.mean():>+10.2f}"
              f"{d6.ex.mean()-d4.ex.mean():>+9.2f}{boot_ci(r4):>+9.2f}{boot_ci(r6):>+9.2f}"
              f"{t4:>8.2f}{t6:>8.2f}")
print(f"  → 60일이 더 높은 칸 {win}/{tot}")

print("\n" + "=" * W)
print("③ 봉우리의 정체 — 문턱을 올릴수록 무엇이 달라지나 (60일 · 잔잔 ≤1.5%)")
print("=" * W)
print(f"  {'문턱':>8}{'건수':>7}{'월수':>6}{'월평균':>9}{'월표준편차':>11}{'t':>7}{'초과':>8}{'승률':>7}{'중앙':>8}")
for rt in UPS:
    d = dd(C(rt, 1.5), 60)
    if len(d) < 60: print(f"  {rt:>6}%↑{len(d):>7}  (부족)"); continue
    r = d.groupby("ym").ex.mean().dropna()
    se = r.std(ddof=1) / math.sqrt(len(r))
    print(f"  {rt:>6}%↑{len(d):>7,}{len(r):>6}{r.mean():>9.2f}{r.std(ddof=1):>11.2f}"
          f"{r.mean()/se:>7.2f}{d.ex.mean():>+8.2f}{(d.r>0).mean()*100:>6.1f}%{d.r.median():>8.2f}")
print("  → t 가 봉우리를 만드는 건 월평균 때문인가 월표준편차 때문인가를 본다.")
print("    표준편차가 튀어서 t 가 떨어지는 거라면 그건 표본 문제지 신호 문제가 아니다.")
