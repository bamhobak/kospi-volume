# -*- coding: utf-8 -*-
"""손절 후보를 **보수 체결**로 다시 판정한다 (2026-09-12).

stop_sweep.py 에서 트레일 -15% 를 전 규칙에 달면 계좌가 23.98 → 28.18배(+17.5%)로 좋아졌다.
그런데 portfolio.py 의 트레일은 '발동가 그대로 체결' 이라는 낙관 가정이다. 실측하니 발동일
종가는 가정보다 중앙 -5.0~-5.5% 아래였다(trail_fill.py). 그 차이를 먹고도 남는지 본다.

  낙관: 보유 중 종가 최고점*(1-t) **그 가격에** 판다
  보수: 그 선을 종가로 깨진 것을 보고 **다음날 시가에** 판다

기준선도 같은 잣대로 다시 재야 공평하다 — 지금 쓰는 P1·P4·P6 트레일도 같은 가정이다.

    python stop_sweep2.py
"""
import sys, warnings, time
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path
BASE = Path(__file__).parent

SRC = (BASE / "portfolio.py").read_text(encoding="utf-8")
HEAD, REST = SRC.split("# 신호를 한 표로 모은다", 1)
MID = "# 신호를 한 표로 모은다" + REST.split("# @@ANALYSIS", 1)[0]

OPT = """        px = np.where(ok, run[np.arange(len(C)), first]*(1-t), C[:, -1])"""
# 패널에 open 열이 없다(메모리 절약). buy 가 곧 '익일 시가' 라 buy.shift(-i) 로 대신한다:
#   buy[t+i] = open[t+i+1] → 발동일(t+first+1) 다음날 시가 = open[t+first+2] = buy[t+first+1]
CONS = """        _O = np.column_stack([g.buy.shift(-i).values for i in range(0, hold+2)])
        px = np.where(ok, _O[np.arange(len(C)), first+1], C[:, -1])
        px = np.where(np.isnan(px), C[:, -1], px)"""
assert MID.count(OPT) == 1
MID_C = MID.replace(OPT, CONS).replace('X["hold"] = (first + 1)[m]', 'X["hold"] = (first + 2)[m]')

ns = {"__file__": str(BASE / "portfolio.py")}
t0 = time.time()
exec(compile(HEAD, "portfolio.py", "exec"), ns)
print(f"패널 적재 {time.time()-t0:.0f}초")
RULES0, TRAIL0 = dict(ns["RULES"]), dict(ns["TRAIL"])
NOSTOP = ["P2", "P3", "P5", "P7", "D1", "D2"]

CFG = [("지금 그대로 (P1·P4·P6만)", None),
       ("+ 전 규칙 트레일 -15%", 0.15),
       ("+ 전 규칙 트레일 -20%", 0.20),
       ("+ 전 규칙 트레일 -25%", 0.25)]

print(f"\n{'설정':<26}{'체결':<7}{'최종':>9}{'연':>8}{'최대낙폭':>10}{'거래':>7}{'기준 대비':>10}")
print("-" * 78)
out = {}
for fill, src in (("낙관", MID), ("보수", MID_C)):
    base = None
    for lbl, trail in CFG:
        ns["RULES"] = dict(RULES0)
        ns["TRAIL"] = dict(TRAIL0) | ({k: trail for k in NOSTOP} if trail else {})
        import io, contextlib
        _b = io.StringIO()
        with contextlib.redirect_stdout(_b):
            exec(compile(src, "portfolio.py", "exec"), ns)
            C, L = ns["simulate"](1.0, 1.0, lbl, quiet=True)
        nav = C.nav.iloc[-1]; mdd = ((C.nav / C.nav.cummax()) - 1).min() * 100
        yrs = len(ns["dates"]) / 252
        if base is None: base = nav
        out[(fill, lbl)] = (nav, (nav ** (1 / yrs) - 1) * 100, mdd, len(L))
        print(f"{lbl:<26}{fill:<7}{nav:>8.2f}배{(nav**(1/yrs)-1)*100:>7.2f}%{mdd:>9.1f}%"
              f"{len(L):>7,}{(nav/base-1)*100:>+9.1f}%")
    print()

print("=" * 78)
print("판정 — 보수 체결에서 기준선 대비")
print("=" * 78)
b = out[("보수", "지금 그대로 (P1·P4·P6만)")]
print(f"  기준선(보수)            {b[0]:.2f}배 · 연 {b[1]:.2f}% · 낙폭 {b[2]:.1f}%")
for lbl, trail in CFG[1:]:
    v = out[("보수", lbl)]
    print(f"  {lbl:<22}{v[0]:>6.2f}배 ({(v[0]/b[0]-1)*100:+.1f}%) · 연 {v[1]:.2f}%"
          f" · 낙폭 {v[2]:.1f}% ({v[2]-b[2]:+.1f}%p)")
print("\n  낙폭이 **깊어지면** 채택하지 않는다 — 목표는 더 버는 게 아니라 덜 아픈 것이다.")
