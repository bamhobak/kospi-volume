# -*- coding: utf-8 -*-
"""강의 2편 마지막 관문 — 쓸 만한 건 하나뿐이니 계좌에서 확인한다.

1·2차에서 살아남은 주장은 M7 하나다: **지수가 월봉 12평(≒240일선) 아래면 그 시장 신규매수 금지**.
지수 단위 실측에서 낙폭 방어는 진짜였다(코스피 -39% vs -67%, 코스닥 -55% vs -88%).
그러나 우리 규칙은 죄다 하락장 진입 규칙이라, 이 게이트는 규칙이 터지는 바로 그때 막을 수 있다.
그러니 규칙 단위가 아니라 **계좌**로 판정한다 — 시드 12개 짝 비교, 늘 쓰던 방식.
  ⓐ 지수 12평 위에서만 매수  ⓑ 지수 12평 아래에서만 매수(반대)  ⓒ 코스피/코스닥 각자 지수로
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

BASE = Path(__file__).parent
SEEDS = 12
src = (BASE / "portfolio.py").read_text(encoding="utf-8")
ns = {"__file__": str(BASE / "portfolio.py")}
real = sys.stdout
sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES, TRAIL = ns["KP"], ns["KQ"], ns["RULES"], ns["TRAIL"]

# 지수 월봉 12평 — 그 달 말 종가가 12개월 이평 위인가. 판정은 월말에만, 다음 달 내내 유지.
def ixgate(code):
    D = fdr.DataReader(code, "2000-01-01")
    D = D[D.Close > 0].copy()
    D["m"] = D.index.strftime("%Y%m")
    M = D.groupby("m").Close.last().to_frame("c")
    M["ma12"] = M.c.rolling(12, min_periods=12).mean()
    M["on"] = M.c > M.ma12
    on = M.on.shift(1)                          # 지난달 말 판정으로 이번 달을 산다(미리보기 없음)
    return dict(zip(M.index, on))
GKP, GKQ = ixgate("KS11"), ixgate("KQ11")
for K, G in ((KP, GKP), (KQ, GKQ)):
    K["ixon"] = K.date.str[:6].map(G)
# [자사주 낙폭] 은 코스피·코스닥 합본 패널(KB)을 쓴다. 여기에도 붙여야 게이트가 걸린다
# (안 붙이면 build2 가 AttributeError 로 죽는다).
KB = ns["KB"]
KB["ixon"] = np.where(KB.mk == "KOSDAQ", KB.date.str[:6].map(GKQ), KB.date.str[:6].map(GKP))

adates = sorted(set(KP.date) | set(KQ.date))
ADI = {d: i for i, d in enumerate(adates)}
rel = (BASE / "rules_relation.py").read_text(encoding="utf-8")
exec(rel[rel.index("def build(R):"):rel.index("S = build(RULES)")], globals())
ta = (BASE / "trail_acct.py").read_text(encoding="utf-8")
exec(ta[ta.index("def build2(trail):"):ta.index("PER = [")].replace(
    "def build2(trail):", "def build2(trail, gate=None):").replace(
    "for rid, (K, hold, stop, pct, mx, cond) in RULES.items():",
    "for rid, (K, hold, stop, pct, mx, cond) in RULES.items():\n"
    "        if gate == 'up':   cond = cond & (K.ixon == True)\n"
    "        if gate == 'down': cond = cond & (K.ixon == False)"), globals())

PER = [("학습 2016~22", "20160101", "20221231"), ("검증 2023~26", "20230101", "20991231"),
       ("기준 2016~", "20160101", "20991231"), ("전구간 2005~26", "20050101", "20991231")]
VAR = [("현행(게이트 없음)", None), ("M7 지수 12평 위에서만", "up"), ("반대: 12평 아래에서만", "down")]

print("=" * 108)
print("계좌 짝 비교 — M7 지수 월봉 12평 게이트 (시드 12)")
print("=" * 108)
print(f"  {'안':<22}" + "".join(f"{p[0]:>26}" for p in PER))
print(f"  {'':<22}" + "".join(f"{'자산':>10}{'낙폭':>8}{'시드승':>8}" for p in PER))
BASE_N = {}
for nm, g in VAR:
    S = build2(TRAIL, g)
    row = ""
    for pn, lo, hi in PER:
        ds = [d for d in adates if lo <= d <= hi]
        R = [sim(S, ds, k) for k in range(SEEDS)]
        nav = [x[0] for x in R]
        md = np.median([x[1] for x in R])
        if g is None:
            BASE_N[pn] = nav; w = "기준"
        else:
            w = f"{sum(a > b for a, b in zip(nav, BASE_N[pn]))}/{SEEDS}"
        row += f"{np.median(nav):>9.2f}배{md:>7.0f}%{w:>8}"
    print(f"  {nm:<22}{row}")
