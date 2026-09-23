# -*- coding: utf-8 -*-
"""[조정매집](P2) 보유 10 → 20일 — **섞는 계좌**로 확인 (2026-09-24).

hold_sweep_kr.py · hold_solo_kr.py 에서 국내 후보 넷 중 20일 [조정매집]만 두 기간 단독 계좌를 모두 이겼다
(A 2005~15 1.07 → 1.10배 · B 2016~ 1.88 → 2.45배, 30/30 시드). 단 A 는 10건뿐이다.
[조정매집]은 국내 비중 18%·자리 2 로 가장 무거운 규칙이라, 돈이 두 배 오래 묶이면 다른 규칙이 살 돈을 뺏을 수 있다.
그래서 portfolio.py 의 simulate(지금 비중·자리·현금 한도 그대로)로 **100시드 짝비교**한다.

    python p2_hold_acct.py
"""
import io, sys, time, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
NS = 100
SRC = (BASE / "portfolio.py").read_text(encoding="utf-8")
HEAD, REST = SRC.split("# 신호를 한 표로 모은다", 1)
MID = "# 신호를 한 표로 모은다" + REST.split("# @@ANALYSIS", 1)[0]
_real = sys.stdout
t0 = time.time()


def log(m):
    print(f"{time.strftime('%H:%M:%S')} {m}", file=sys.stderr, flush=True)


ns = {"__file__": str(BASE / "portfolio.py")}
sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(HEAD, "portfolio.py", "exec"), ns)
S = {}
for h in (10, 20):
    r = list(ns["RULES"]["P2"]); r[1] = h
    ns["RULES"]["P2"] = tuple(r)
    exec(compile(MID, "portfolio.py", "exec"), ns)
    S[h] = ns["S"].copy()
sys.stdout = _real
sys.stdout.reconfigure(encoding="utf-8")
sim = ns["simulate"]
log("신호 준비 끝")


def one(z):
    ns["S"] = z
    C, L = sim(1.0, 1.0, "", quiet=True)
    nav = C.nav.values
    a = C[C.date <= "20151231"].nav
    b = C[C.date >= "20160101"].nav
    mdd = lambda s: ((s / s.cummax()) - 1).min() * 100
    return (nav[-1], mdd(C.nav), a.iloc[-1], mdd(a), b.iloc[-1] / b.iloc[0], mdd(b / b.iloc[0]),
            C.expo.mean() * 100)


R = {}
for h in (10, 20):
    z = S[h]
    R[h] = np.array([one(z.sample(frac=1.0, random_state=s).sort_values("di", kind="stable").reset_index(drop=True))
                     for s in range(NS)])
    log(f"  {h}일 끝")
ns["S"] = S[10]

print(f"\n## [조정매집] 보유 10 vs 20 — 국내 섞는 계좌 ({NS}시드 짝비교 · 지금 비중·자리 그대로)\n")
print("| 보유 | 전체 2005~ 배수 | 최대낙폭 | A 2005~15 배수 | A 낙폭 | B 2016~ 배수 | B 낙폭 | 평균 노출 |")
print("|---|---|---|---|---|---|---|---|")
for h in (10, 20):
    m = np.median(R[h], axis=0)
    print(f"| {h}일{' (지금)' if h == 10 else ''} | {m[0]:.2f}배 | {m[1]:.1f}% | {m[2]:.2f}배 | {m[3]:.1f}% | "
          f"{m[4]:.2f}배 | {m[5]:.1f}% | {m[6]:.0f}% |")
w = lambda k, hi=True: ((R[20][:, k] > R[10][:, k]) if hi else (R[20][:, k] > R[10][:, k])).mean() * 100
print(f"\n20일이 이긴 시드 — 전체 배수 {w(0):.0f}% · 전체 낙폭 {w(1):.0f}% · A 배수 {w(2):.0f}% · A 낙폭 {w(3):.0f}% · "
      f"B 배수 {w(4):.0f}% · B 낙폭 {w(5):.0f}%  (낙폭은 덜 깊은 쪽이 이김)")
log(f"끝 ({(time.time() - t0) / 60:.1f}분)")
