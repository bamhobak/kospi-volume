# -*- coding: utf-8 -*-
"""**유동성 대응 — 문턱 대신 비중으로** (2026-09-15).

앞선 실측(liquidity_3e.py)에서 나온 것:
  · 3억이면 계좌가 20.14 → **14.17배**로 30% 깎인다(슬리피지 반영).
  · 범인은 **[조정매집] 하나**다 — 거래의 **69%**가 일 거래대금의 5%를 넘긴다
    (중앙 충격 8.81% · 하위10% 때 16.75%). 나머지 8규칙은 0~10%.
    신호 172건에 자리 2개라 경쟁이 없어 작은 종목도 그냥 사는데, 비중은 18%로 제일 크다.
  · **유니버스 문턱을 올리면 더 나빠진다**(14.17 → 9.35 → 6.69배). 좋은 신호가 통째로 날아간다.

그러면 남은 손잡이는 **비중**이다. 좋은 신호를 버리지 않고 종목당 금액만 줄인다.
시장충격은 √참여율이라 비중을 절반으로 줄이면 충격은 √2배(약 30%)만 준다 — 그래도
슬리피지는 **거래당** 붙으므로 총액 기준으로는 절반이 된다.

⚠ 공짜가 아니다. 비중을 낮추면 **노출도 줄어** 슬리피지가 없어도 수익이 준다.
   그래서 **슬리피지 없는 판과 있는 판을 나란히** 놓아야 순효과가 보인다.

  ① [조정매집] 비중별 — 슬리피지 없음 vs 3억
  ② 위험 3규칙을 같이 조정
  ③ 계좌 크기별 최적 비중
  ④ 낮춘 비중을 다른 규칙에 돌려주면

    python liquidity_pct.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
W = 116
SEEDS = 8
KIMP = 0.30          # 제곱근 시장충격 계수 (왕복 2회)
NAME = {"P1": "조용한 신고가", "P2": "조정매집", "P3": "폭락반등", "P4": "업종붕괴 이탈",
        "P5": "자사주 낙폭", "P6": "깊은 이격", "P7": "외인 매집",
        "D1": "낙폭과대", "D2": "저PBR 낙폭"}
PCT0 = {"P1": 14.4, "P2": 18, "P3": 6, "P4": 3.6, "P5": 6, "P6": 4.8, "P7": 4.8, "D1": 6, "D2": 6}
t0 = time.time()


def sec(t):
    print("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


SRC = (BASE / "portfolio.py").read_text(encoding="utf-8")
HEAD, REST = SRC.split("# 신호를 한 표로 모은다", 1)
MID = "# 신호를 한 표로 모은다" + REST.split("# @@ANALYSIS", 1)[0]
ns = {"__file__": str(BASE / "portfolio.py")}
exec(compile(HEAD, "portfolio.py", "exec"), ns)
exec(compile(MID, "portfolio.py", "exec"), ns)
S0, simulate = ns["S"], ns["simulate"]
print("신호 %s건" % f"{len(S0):,}")


def shuffled(Z, seed):
    return Z.sample(frac=1.0, random_state=seed).sort_values("di", kind="stable").reset_index(drop=True)


def make(pcts, cap=None):
    """비중표를 갈아 끼우고, cap(만원)이 있으면 그 계좌 크기의 슬리피지를 비용에 더한다."""
    z = S0.copy()
    z["pct"] = z.rid.map(pcts).astype(float)
    if cap:
        part = (cap * z.pct / 100) / (z.amt20.astype(float) * 10000) * 100
        z["cost"] = z.cost + KIMP * np.sqrt(np.maximum(part.fillna(0), 0)) * 2
    return z


def run(pcts, cap=None, seeds=SEEDS):
    z = make(pcts, cap)
    ns["S"] = z
    C, L = simulate(1.0, 1.0, "", quiet=True)
    nav = C.nav.iloc[-1]
    mdd = ((C.nav / C.nav.cummax()) - 1).min() * 100
    expo = C.expo.mean() * 100
    med = np.median([(ns.__setitem__("S", shuffled(z, s)),
                      simulate(1.0, 1.0, "", quiet=True)[0].nav.iloc[-1])[1]
                     for s in range(seeds)])
    return nav, mdd, expo, med


sec("① [조정매집] 비중별 — 슬리피지 없음 vs 3억 계좌")
print("  %-16s%10s%9s%9s%12s   |%10s%9s%12s"
      % ("[조정매집] 비중", "노출", "자산", "낙폭", "시드중앙", "자산", "낙폭", "시드중앙"))
print("  %-16s%40s   |%31s" % ("", "── 슬리피지 없음 ──", "── 3억 ──"))
BEST = None
for p in (18, 15, 12, 9, 6, 3):
    pc = dict(PCT0); pc["P2"] = p
    n0, m0, e0, d0 = run(pc)
    n3, m3, e3, d3 = run(pc, 30000)
    star = ""
    if BEST is None or d3 > BEST[1]:
        BEST = (p, d3); star = ""
    print("  %-16s%9.0f%%%8.2f배%8.1f%%%11.2f배   |%9.2f배%8.1f%%%11.2f배%s"
          % ("%d%%" % p, e0, n0, m0, d0, n3, m3, d3, star))
print("  ※ 왼쪽은 '유동성이 무한할 때', 오른쪽은 '3억으로 실제 굴릴 때' 다.")

sec("② 위험 3규칙을 같이 — [조정매집]·[낙폭과대]·[자사주 낙폭]")
print("  (충격 5% 넘는 거래 비율: 조정매집 69% · 낙폭과대 10% · 자사주 낙폭 7%)\n")
print("  %-28s%9s%9s%12s" % ("구성 (3억 기준)", "자산", "낙폭", "시드중앙"))
CFG = [("지금 (18 / 6 / 6)", {}),
       ("조정매집만 9", {"P2": 9}),
       ("조정매집 9 · 낙폭과대 4", {"P2": 9, "D1": 4}),
       ("조정매집 9 · 낙폭과대 4 · 자사주 4", {"P2": 9, "D1": 4, "P5": 4}),
       ("조정매집 6 · 낙폭과대 4 · 자사주 4", {"P2": 6, "D1": 4, "P5": 4})]
for lbl, ov in CFG:
    pc = dict(PCT0); pc.update(ov)
    n, m, e, d = run(pc, 30000)
    print("  %-28s%8.2f배%8.1f%%%11.2f배" % (lbl, n, m, d))

sec("③ 계좌 크기별 — [조정매집] 비중을 얼마로 둘까")
print("  %-12s" % "계좌" + "".join("%12s" % ("P2 %d%%" % p) for p in (18, 12, 9, 6)))
for cap, lbl in ((10000, "1억"), (30000, "3억"), (50000, "5억"), (100000, "10억")):
    row = ""
    for p in (18, 12, 9, 6):
        pc = dict(PCT0); pc["P2"] = p
        _, _, _, d = run(pc, cap)
        row += "%11.2f배" % d
    print("  %-12s%s" % (lbl, row))

sec("④ 낮춘 비중을 다른 규칙에 돌려주면 (3억)")
print("  [조정매집] 18→9 로 아낀 자리를 노출이 남는 규칙에 준다\n")
print("  %-34s%9s%9s%9s%12s" % ("구성", "노출", "자산", "낙폭", "시드중앙"))
for lbl, ov in [("조정매집 9 (남은 건 안 씀)", {"P2": 9}),
                ("조정매집 9 · 깊은이격 4.8→6", {"P2": 9, "P6": 6}),
                ("조정매집 9 · 업종붕괴 3.6→5", {"P2": 9, "P4": 5}),
                ("조정매집 9 · 외인매집 4.8→6", {"P2": 9, "P7": 6}),
                ("조정매집 9 · 셋 다 올림", {"P2": 9, "P6": 6, "P4": 5, "P7": 6})]:
    pc = dict(PCT0); pc.update(ov)
    n, m, e, d = run(pc, 30000)
    print("  %-34s%8.0f%%%8.2f배%8.1f%%%11.2f배" % (lbl, e, n, m, d))
print("\n총 %.0f초" % (time.time() - t0))
