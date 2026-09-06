# -*- coding: utf-8 -*-
"""후보안 4단계 — 계좌로 확인한다. 규칙 하나만 갈아 끼우고 21년을 다시 산다.

규칙 단위 성적은 '자리 경쟁' 을 무시한다. 신호를 40% 줄이면 규칙 평균은 오르지만 계좌는
빈 자리를 놀리게 되어 오히려 손해일 수 있다(2026-09-05 공매도×프로그램에서 실제로 그랬다).
같은 시드로 짝지어 비교한다.
사용: IX_FROM=2004-06-01 DART_FROM=20040101 PANEL_KP=panel_kp.pkl PANEL_KQ=panel_kq.pkl python why_lose4.py [--seeds 12]
"""
import io, os, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
arg = lambda k, d: sys.argv[sys.argv.index(k)+1] if k in sys.argv else d
SEEDS = int(arg("--seeds", "12"))
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES = ns["KP"], ns["KQ"], ns["RULES"]
adates = sorted(set(KP.date) | set(KQ.date)); ADI = {d: i for i, d in enumerate(adates)}
rel = (BASE/"rules_relation.py").read_text(encoding="utf-8")
exec(rel[rel.index("def build(R):"):rel.index("S = build(RULES)")], globals())
exec(rel[rel.index("def sim(S, ds, seed):"):rel.index("ds = [d for d in adates")].replace(
     "return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid)",
     "return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid, curve=Cv)"), globals())

def variant(**patch):
    """RULES 를 복사해 일부만 갈아 끼운다. patch = {rid: (cond, hold)}"""
    R = dict(RULES)
    for rid, (cond, hold) in patch.items():
        P, h0, stop, pct, mx, _ = R[rid]
        R[rid] = (P, hold or h0, stop, pct, mx, cond)
    return build(R)

VAR = {
  "현행": {},
  "폭락반등 -25%": {"P3": (RULES["P3"][5] & (KP.ret20 <= -25), None)},
  "폭락반등 -25%·15일": {"P3": (RULES["P3"][5] & (KP.ret20 <= -25), 15)},
  "낙폭과대 -25%": {"D1": (RULES["D1"][5] & (KQ.ret20 <= -25), None)},
  "낙폭과대 -30%": {"D1": (RULES["D1"][5] & (KQ.ret20 <= -30), None)},
  "둘 다(-25/-30)": {"P3": (RULES["P3"][5] & (KP.ret20 <= -25), None),
                     "D1": (RULES["D1"][5] & (KQ.ret20 <= -30), None)},
}
PER = [("2005~07","20050101","20071231"), ("2008~09","20080101","20091231"),
       ("2010~12","20100101","20121231"), ("2013~17","20130101","20171231"),
       ("2018~22","20180101","20221231"), ("2023~26","20230101","20991231"),
       ("전체","20050101","20991231")]
print(f"② 계좌 시뮬 — 같은 시드 {SEEDS}개로 짝 비교 (자산 배수 중앙값 / 최대낙폭)")
print(f"  {'안':<20}" + "".join(f"{p[0]:>15}" for p in PER))
print("  " + "-"*125)
BASE_R = {}
for nm, patch in VAR.items():
    S = variant(**patch); row = ""
    for pn, lo, hi in PER:
        ds = [d for d in adates if lo <= d <= hi]
        R = [sim(S, ds, k) for k in range(SEEDS)]
        nav = np.median([r["nav"] for r in R]); mdd = np.median([r["mdd"] for r in R])
        row += f"{nav:>8.2f}배{mdd:>6.0f}%"
        if nm == "현행": BASE_R[pn] = [r["nav"] for r in R]
        elif pn == "전체":
            w = sum(a > b for a, b in zip([r["nav"] for r in R], BASE_R[pn]))
            row += f"  (현행보다 나음 {w}/{SEEDS})"
    print(f"  {nm:<20}{row}")
