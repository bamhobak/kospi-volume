# -*- coding: utf-8 -*-
"""**노출을 늘리는 두 가지 방법 중 무엇이 나은가** (2026-09-15).

slot_lab2 에서 '비중 유지 · 자리만 늘리기' 가 12/12 자산승이 났다(15.99→19.10배).
그런데 노출도 25%→28% 로 같이 올랐고 낙폭은 -10.7%→-16.0% 로 나빠졌다.
**그냥 노출을 늘린 것과 뭐가 다른가** 를 가리지 않으면 발견이 아니다.

노출을 올리는 손잡이는 둘이다.
  ① 비중 ×s  — 종목당 더 크게. 들고 있는 **종목 수는 그대로**라 집중도가 오른다.
  ② 자리 ×k  — 같은 크기로 **더 많은 종목**을. 분산이 는다.
둘 다 노출을 올리므로, **같은 노출에서** 견줘야 어느 손잡이가 좋은지 알 수 있다.

그래서 k×s 격자를 훑고 노출로 보간해 같은 자리에 세운다.

    python slot_lab3.py           (시드 12)
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
SEEDS = int(sys.argv[1]) if len(sys.argv) > 1 else 12
W = 100


def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)


SRC = (BASE / "portfolio.py").read_text(encoding="utf-8").split("# @@ANALYSIS", 1)[0]
ns = {"__file__": str(BASE / "portfolio.py")}
t0 = time.time()
exec(compile(SRC, "portfolio.py", "exec"), ns)
S0, simulate = ns["S"], ns["simulate"]
print(f"패널·신호 준비 {time.time()-t0:.0f}초")

KS = (1, 1.5, 2, 3)          # 자리 배수
SS = (0.6, 0.8, 1.0, 1.2, 1.5)   # 비중 배율
SLOT = {}
for k in KS:
    z = S0.copy()
    if k != 1: z["mx"] = np.maximum(1, np.round(z.mx * k)).astype(int)
    SLOT[k] = z

sec("① 격자 — 자리 배수 × 비중 배율")
print("  각 칸은 (실제노출 · 최종자산 · 최대낙폭). 노출이 같은 칸끼리 견주는 게 요점이다.\n")
G = {}
print(f"  {'자리':<6}" + "".join(f"{'비중 '+str(s)+'x':>22}" for s in SS))
for k in KS:
    row = ""
    for s in SS:
        ns["S"] = SLOT[k]
        C, L = simulate(1.0, s, "", quiet=True)
        e = C.expo.mean() * 100
        n = C.nav.iloc[-1]
        m = ((C.nav / C.nav.cummax()) - 1).min() * 100
        G[(k, s)] = (e, n, m)
        row += f"{e:>7.0f}%{n:>8.2f}배{m:>7.1f}%"
    print(f"  {str(k)+'x':<6}{row}")


def at(k, tgt):
    """자리 k 줄에서 노출이 tgt 가 되는 지점의 (자산, 낙폭) — 비중 배율로 보간."""
    p = sorted((G[(k, s)] for s in SS))
    xs = [a[0] for a in p]
    if tgt < xs[0] or tgt > xs[-1]: return None
    for i in range(len(p) - 1):
        if xs[i] <= tgt <= xs[i + 1]:
            w = (tgt - xs[i]) / max(xs[i + 1] - xs[i], 1e-9)
            return p[i][1] + w * (p[i + 1][1] - p[i][1]), p[i][2] + w * (p[i + 1][2] - p[i][2])


sec("② 같은 노출에 세워 놓고 — 어느 손잡이가 나은가")
print(f"  {'노출':<8}" + "".join(f"{'자리 '+str(k)+'x':>24}" for k in KS))
for tgt in (25, 28, 30, 33, 36):
    row = ""
    for k in KS:
        v = at(k, tgt)
        row += (f"{v[0]:>13.2f}배{v[1]:>9.1f}%" if v else f"{'—':>24}")
    print(f"  {str(tgt)+'%':<8}{row}")
print("\n  ※ 같은 줄(같은 노출)에서 오른쪽으로 갈수록 자산이 늘고 낙폭이 줄면")
print("    '자리를 늘리는 쪽' 이 '비중을 키우는 쪽' 보다 낫다는 뜻이다.")


def shuffled(Z, seed):
    return Z.sample(frac=1.0, random_state=seed).sort_values("di", kind="stable").reset_index(drop=True)


sec(f"③ 노출을 맞춘 짝비교 ({SEEDS}시드) — 기준과 같은 노출에서 자리만 늘린다")
# 기준 노출에 맞는 비중 배율을 자리 배수마다 이분법으로 찾는다
base_e = G[(1, 1.0)][0]
print(f"  기준 노출 {base_e:.0f}% 에 맞춰 비중을 낮춘다 (자리를 늘린 만큼 종목당은 작게)")
print(f"\n  {'구성':<24}{'비중배율':>9}{'노출':>7}{'중앙':>9}{'최악':>9}{'최고':>9}{'폭':>7}{'자산승':>8}{'낙폭승':>8}")
for k in KS:
    lo, hi = 0.2, 1.5
    for _ in range(14):
        mid = (lo + hi) / 2
        ns["S"] = SLOT[k]
        C, _ = simulate(1.0, mid, "", quiet=True)
        if C.expo.mean() * 100 < base_e: lo = mid
        else: hi = mid
    sc = (lo + hi) / 2
    rows = []
    for s in range(SEEDS):
        ns["S"] = shuffled(S0, s);      x, _ = simulate(1.0, 1.0, "", quiet=True)
        ns["S"] = shuffled(SLOT[k], s); y, _ = simulate(1.0, sc, "", quiet=True)
        rows.append((y.nav.iloc[-1], x.nav.iloc[-1],
                     ((y.nav/y.nav.cummax())-1).min()*100, ((x.nav/x.nav.cummax())-1).min()*100,
                     y.expo.mean()*100))
    R = pd.DataFrame(rows, columns=["nav", "base", "mdd", "bmdd", "expo"])
    print(f"  {f'자리 {k}배 · 노출맞춤':<24}{sc:>9.2f}{R.expo.mean():>6.0f}%"
          f"{R.nav.median():>8.2f}배{R.nav.min():>8.2f}배{R.nav.max():>8.2f}배"
          f"{R.nav.max()/R.nav.min():>6.2f}x{int((R.nav>R.base).sum()):>6}/{SEEDS}"
          f"{int((R.mdd>R.bmdd).sum()):>6}/{SEEDS}")

print(f"\n총 {time.time()-t0:.0f}초")
