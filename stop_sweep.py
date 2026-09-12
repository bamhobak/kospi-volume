# -*- coding: utf-8 -*-
"""**스탑 없는 6규칙에 손절을 달면 나아지나** (2026-09-12).

물음: "[저PBR 낙폭] 최악 -97.4%(플렉스컴 폐지) 같은 건 손절이 있었으면 그 전에 끊기지 않나?"

맞다 — 그 한 건은 끊긴다. 플렉스컴은 매수가 2,110원에서 2주 넘게 1,540~1,675원(-21~-27%)
에 머물다가 거래정지 뒤 520원으로 열렸다. -15% 든 -25% 든 정지 전에 나왔다.
문제는 **그 한 건을 살리는 대가로 나머지를 얼마나 잃느냐** 다. 낙폭 규칙은 떨어지는 것을
사서 되돌림을 먹는 규칙이라, 손절은 바닥에서 정확히 털려 나가게 만들 수 있다.

  ① 규칙 단위 — 손절 후보별 평균·중앙·승률·최악 (기준 2016~26, 중복 제거)
  ② 계좌 단위 — 같은 설정으로 계좌 전체를 돌린다. **판정은 여기서 한다.**
  ③ 플렉스컴 한 건이 실제로 끊기는지 확인

⚠ 고정 손절은 '보유 중 저가가 손절선을 찍으면 **그 가격에** 팔린다' 고 본다(낙관).
   갭하락·하한가면 못 받는다. 그래서 여기서 나오는 손절의 이득은 **상한**이다.

    python stop_sweep.py
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

ns = {"__file__": str(BASE / "portfolio.py")}
t0 = time.time()
exec(compile(HEAD, "portfolio.py", "exec"), ns)
print(f"패널 적재 {time.time()-t0:.0f}초")
RULES0, TRAIL0 = dict(ns["RULES"]), dict(ns["TRAIL"])
NOSTOP = ["P2", "P3", "P5", "P7", "D1", "D2"]          # 지금 스탑이 없는 여섯
NAME = {"P7": "외인 매집", "P1": "조용한 신고가", "P4": "업종붕괴 이탈", "P6": "깊은 이격",
        "P3": "폭락반등", "P2": "조정매집", "D1": "낙폭과대", "D2": "저PBR 낙폭", "P5": "자사주 낙폭"}

CFG = [("지금 그대로", None, None),
       ("고정 손절 -15%", 0.15, None), ("고정 손절 -20%", 0.20, None), ("고정 손절 -25%", 0.25, None),
       ("트레일 -15%", None, 0.15), ("트레일 -20%", None, 0.20), ("트레일 -25%", None, 0.25)]


def apply(stop, trail):
    """스탑 없는 여섯 규칙에만 손절/트레일을 달아 S 를 다시 만든다."""
    ns["RULES"] = {k: ((v[0], v[1], stop, v[3], v[4], v[5]) if (k in NOSTOP and stop) else v)
                   for k, v in RULES0.items()}
    ns["TRAIL"] = dict(TRAIL0) | ({k: trail for k in NOSTOP} if trail else {})
    exec(compile(MID, "portfolio.py", "exec"), ns)
    return ns["S"], ns["simulate"]


# 중복 제거 — stats_2016.py 와 같은 방식, 기준구간 2016~
def dedup(z, hold_col="hold"):
    z = z.sort_values("di")
    keep, last = [], {}
    for t, i, ix, h in zip(z.ticker.values, z.di.values, z.index, z[hold_col].values):
        if last.get(t, -10**9) >= i: continue
        last[t] = i + int(h); keep.append(ix)
    return z.loc[keep]


rows = {}
acct = []
for lbl, stop, trail in CFG:
    S, simulate = apply(stop, trail)
    S = S.copy()
    hit = (S.stop.notna() & ((S.low / S.buy - 1) * 100 <= -S.stop * 100))
    S["ret"] = np.where(hit, -S.stop.fillna(0) * 100 - S.cost, (S.exit / S.buy - 1) * 100 - S.cost)
    Z = dedup(S[(S.date >= "20160101")])
    for rid in NOSTOP:
        z = Z[Z.rid == rid]
        if not len(z): continue
        rows.setdefault(rid, []).append(
            (lbl, len(z), z.ret.mean(), z.ret.median(), (z.ret > 0).mean() * 100, z.ret.min()))
    C, L = simulate(1.0, 1.0, lbl, quiet=True)
    mdd = ((C.nav / C.nav.cummax()) - 1).min() * 100
    yrs = len(ns["dates"]) / 252
    acct.append((lbl, C.nav.iloc[-1], (C.nav.iloc[-1] ** (1 / yrs) - 1) * 100, mdd, len(L)))
    print(f"  {lbl:<14} 계좌 {C.nav.iloc[-1]:>6.2f}배 · 연 {acct[-1][2]:>5.2f}% · 낙폭 {mdd:>6.1f}%")

W = 96
print("\n" + "=" * W)
print("① 규칙 단위 — 기준구간 2016~26 · 중복 제거")
print("=" * W)
for rid in NOSTOP:
    if rid not in rows: continue
    print(f"\n  {NAME[rid]}")
    print(f"    {'설정':<16}{'건수':>6}{'평균':>9}{'중앙':>9}{'승률':>7}{'최악':>9}")
    for lbl, n, a, m, w, wo in rows[rid]:
        print(f"    {lbl:<16}{n:>6,}{a:>+8.2f}%{m:>+8.2f}%{w:>6.0f}%{wo:>+8.1f}%")

print("\n" + "=" * W)
print("② 계좌 단위 — 여기서 판정한다")
print("=" * W)
print(f"  {'설정':<16}{'최종':>8}{'연':>8}{'최대낙폭':>10}{'거래':>7}{'기준 대비':>10}")
base = acct[0][1]
for lbl, nav, cagr, mdd, n in acct:
    print(f"  {lbl:<16}{nav:>7.2f}배{cagr:>7.2f}%{mdd:>9.1f}%{n:>7,}{(nav/base-1)*100:>+9.1f}%")

print("\n" + "=" * W)
print("③ 플렉스컴(065270) 2016-02-23 매수분 — 손절이 실제로 끊나")
print("=" * W)
for lbl, stop, trail in CFG:
    S, _ = apply(stop, trail)
    z = S[(S.ticker == "065270") & (S.date >= "20160215") & (S.date <= "20160301")]
    if not len(z):
        print(f"  {lbl:<16} 신호 없음"); continue
    r = z.iloc[0]
    hitp = (r.stop == r.stop) and (r.low / r.buy - 1) * 100 <= -r.stop * 100
    ret = (-r.stop * 100 - r.cost) if hitp else (r.exit / r.buy - 1) * 100 - r.cost
    print(f"  {lbl:<16} 매수 {r.buy:,.0f}원 → 청산 {ret:+.1f}%")
