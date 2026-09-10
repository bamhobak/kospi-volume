# -*- coding: utf-8 -*-
"""마지막 확인 — 낙폭 -7%p 개선이 시드 노이즈인가.

us_tech5.py 에서 노출을 맞춰 견주니 배수는 구간마다 뒤집혔는데(학습은 지고 검증은 이김)
**최대낙폭만은 -55% → -48% 로 일관되게 좋았다**. 이게 시드 30개의 중앙값이라
'우연히 좋은 시드가 뽑힌 것' 일 수 있다. 시드별 분포를 통째로 보고 판정한다.

우리 목표는 지수를 이기는 게 아니라 **오를 때 적당히 · 내릴 때 안전**이므로
([[goal-not-beating-index]] · [[rule-stability-first]]), 낙폭 개선이 진짜라면
배수가 비겨도 채택 근거가 된다. 반대로 노이즈면 채택할 이유가 없다.

    python us_tech6.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
src = open(BASE / "us_tech5.py", encoding="utf-8").read()
src = src.split('W = 132')[0].split('"""', 2)[2]          # 준비 부분만 빌려 쓴다
exec(src)
SEEDS = 60

PAIRS = [
    ("노출 60%", ("A+ N1 12%x5", {"N1": (12, 5), "D1": (5, 3), "D2": (5, 3)}),
                 ("E  + 잔잔120·60일 10%x3", {"N1": (10, 4), "D1": (5, 3), "D2": (5, 3), "FG6": (10, 3)})),
    ("노출 68%", ("A+ N1 12%x6", {"N1": (12, 6), "D1": (5, 3), "D2": (5, 3)}),
                 ("E+ + 잔잔120·60일 10%x5", {"N1": (10, 4), "D1": (5, 3), "D2": (5, 3), "FG6": (10, 5)})),
    ("노출 75%", ("A+ N1 10%x8", {"N1": (10, 8), "D1": (5, 3), "D2": (5, 3)}),
                 ("E++ 잔잔120·60일 10%x6", {"N1": (10, 5), "D1": (5, 3), "D2": (5, 3), "FG6": (10, 6)})),
]
DS = [d for d in dates if d >= "20050101"]
W = 128
print("\n" + "=" * W)
print(f"시드 {SEEDS}개 분포 — 중앙값이 아니라 퍼짐을 본다 (전구간 2005~26)")
print("=" * W)
print(f"  {'구성':<30}{'노출':>6}{'배수 중앙':>10}{'하위25%':>9}{'상위25%':>9}"
      f"{'낙폭 중앙':>10}{'낙폭 최악':>10}{'낙폭 최선':>10}")
res = {}
for lab, (na, aa), (nb, ab) in PAIRS:
    print(f"  ── {lab} ──")
    for nm, al in ((na, aa), (nb, ab)):
        S = build(al)
        R = [sim(S, DS, k) for k in range(SEEDS)]
        nav = np.array([x[0] for x in R]); mdd = np.array([x[1] for x in R])
        exp = np.median([x[2] for x in R]) * 100
        res[nm] = (nav, mdd)
        print(f"  {nm:<30}{exp:>5.0f}%{np.median(nav):>9.2f}배{np.percentile(nav,25):>9.2f}"
              f"{np.percentile(nav,75):>9.2f}{np.median(mdd):>9.1f}%{mdd.min():>9.1f}%{mdd.max():>9.1f}%")
    a, b = res[na][1], res[nb][1]
    # 시드는 짝지어 비교할 수 있다 — 같은 시드는 같은 무작위 순서를 쓴다
    d = b - a                     # 양수면 후보 쪽 낙폭이 얕다(낙폭은 음수값)
    win = (d > 0).mean() * 100
    print(f"     → 낙폭 차이 중앙 {np.median(d):+.1f}%p · 후보가 얕은 시드 {win:.0f}% "
          f"({int((d>0).sum())}/{SEEDS})")
    dn = res[nb][0] - res[na][0]
    print(f"     → 배수 차이 중앙 {np.median(dn):+.2f}배 · 후보가 높은 시드 "
          f"{(dn>0).mean()*100:.0f}% ({int((dn>0).sum())}/{SEEDS})")
    print()

print("=" * W)
print("최악 1년 — 계좌가 실제로 겪는 고통은 낙폭보다 '제자리 걸음' 이다")
print("=" * W)
def worst1y(S, seeds=20):
    out = []
    for k in range(seeds):
        rng = np.random.default_rng(k); nav, held = 1.0, {}
        byd = {d: gg for d, gg in S.groupby("date")}
        curve = []
        for d in DS:
            di = ADI[d]
            for kk in [kk for kk, v in held.items() if v[0] <= di]:
                nav *= 1 + held.pop(kk)[1] / 100
            gg = byd.get(d)
            if gg is not None:
                for r in gg.sample(frac=1, random_state=int(rng.integers(1 << 30))).itertuples():
                    kk = (r.rid, r.ticker)
                    if kk in held: continue
                    if sum(1 for x in held if x[0] == r.rid) >= r.mx: continue
                    if sum(v[2] for v in held.values()) / 100 + r.pct / 100 > 1.0: continue
                    held[kk] = (di + int(r.hold), r.ret * r.pct / 100, r.pct)
            curve.append(nav)
        c = pd.Series(curve)
        out.append((c / c.shift(252) - 1).min() * 100)
    return np.median(out)
for lab, (na, aa), (nb, ab) in PAIRS:
    wa, wb = worst1y(build(aa)), worst1y(build(ab))
    print(f"  {lab:<10} {na:<30}{wa:>8.1f}%    {nb:<30}{wb:>8.1f}%   차이 {wb-wa:+.1f}%p")
