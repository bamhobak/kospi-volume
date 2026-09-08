# -*- coding: utf-8 -*-
"""채널 필터를 기존 규칙에 얹으면 계좌가 나아지나 — 결정적 관문.

대조군(chan_ctrl.py)에서 '하락채널 하단이탈' 이 우리 재료(업종붕괴+이격) 위에 얹혔을 때
규칙 단위로는 보탬이 있었다(코스피 5일 절삭 -0.25→+0.07, CI +0.14→+0.85, 양수해 9→11/11).
그러나 규칙 단위 통과는 절반이다. [업종붕괴 이탈] 조이기 20개가 전부 자리제한 착시로
기각된 전례가 있다([[p4-tighten-rejected]]). 계좌로 판정한다.

얹을 곳: P4(업종붕괴 이탈)·P6(깊은 이격) — 둘 다 업종 -20% 와 이격을 쓰는 코스피 규칙이다.
조건: 60일 회귀채널 기울기 < -20(연율%) 이고 위치 pos ≤ -1.5(하단 밖 종가 마감).
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import verdict
BASE = Path(__file__).parent; SEEDS = 12
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, KB, RULES, TRAIL = ns["KP"], ns["KQ"], ns["KB"], ns["RULES"], ns["TRAIL"]

def chan(K, L=60):
    g = K.groupby("ticker", sort=False)
    y = np.log(K.close.clip(lower=1)); idx = g.cumcount().astype(float); z = idx*y
    S1 = y.groupby(K.ticker).transform(lambda s: s.rolling(L, min_periods=L).sum())
    Sz = z.groupby(K.ticker).transform(lambda s: s.rolling(L, min_periods=L).sum())
    Vy = y.groupby(K.ticker).transform(lambda s: s.rolling(L, min_periods=L).var(ddof=0))
    ybar = S1/L; Sxy = Sz - (idx-(L-1))*S1
    tbar = (L-1)/2.0; Stt = (L-1)*L*(2*L-1)/6.0
    slope = (Sxy - L*tbar*ybar)/(Stt - L*tbar**2)
    sd = np.sqrt(np.clip(Vy - slope**2*((L*L-1)/12.0), 1e-12, None))
    K["cpos"] = (y - (ybar + slope*(L-1-tbar)))/sd
    K["cslope"] = slope*100*250
    return K
for K in (KP, KQ, KB): chan(K)
for K in (KP, KQ, KB):
    K["cfil"] = (K.cslope < -20) & (K.cpos <= -1.5)

adates = sorted(set(KP.date)|set(KQ.date)); ADI = {d:i for i,d in enumerate(adates)}
rel = (BASE/"rules_relation.py").read_text(encoding="utf-8")
exec(rel[rel.index("def build(R):"):rel.index("S = build(RULES)")], globals())
ta = (BASE/"trail_acct.py").read_text(encoding="utf-8")
exec(ta[ta.index("def build2(trail):"):ta.index("PER = [")].replace(
     "def build2(trail):", "def build2(trail, on=()):").replace(
     "for rid, (K, hold, stop, pct, mx, cond) in RULES.items():",
     "for rid, (K, hold, stop, pct, mx, cond) in RULES.items():\n"
     "        if rid in on: cond = cond & (K.cfil == True)"), globals())

PER = [("학습 2016~22","20160101","20221231"), ("검증 2023~26","20230101","20991231"),
       ("기준 2016~","20160101","20991231"), ("전구간 2005~26","20050101","20991231")]
print("="*112); print("채널 필터를 기존 규칙에 얹으면 (시드 12)"); print("="*112)
print(f"  {'안':<22}" + "".join(f"{p[0]:>22}" for p in PER))
print(f"  {'':<22}" + "".join(f"{'자산':>9}{'낙폭':>6}{'시드승':>7}" for p in PER))
B = {}; row = ""
S0 = build2(TRAIL)
for pn, lo, hi in PER:
    ds = [d for d in adates if lo <= d <= hi]
    R = [sim(S0, ds, k) for k in range(SEEDS)]
    B[pn] = [x[0] for x in R]
    row += f"{np.median(B[pn]):>8.2f}배{np.median([x[1] for x in R]):>5.0f}%{'기준':>7}"
print(f"  {'현행':<22}{row}")
NT = 0
for on, nm in ((("P6",),"깊은 이격에 얹기"), (("P4",),"업종붕괴 이탈에 얹기"),
               (("P4","P6"),"둘 다에 얹기")):
    NT += 1
    S = build2(TRAIL, on); row = ""
    for pn, lo, hi in PER:
        ds = [d for d in adates if lo <= d <= hi]
        R = [sim(S, ds, k) for k in range(SEEDS)]
        nav = [x[0] for x in R]
        w = sum(a>b for a,b in zip(nav, B[pn]))
        row += f"{np.median(nav):>8.2f}배{np.median([x[1] for x in R]):>5.0f}%{w:>5}/{SEEDS}"
    print(f"  {nm:<22}{row}")
    z = S[S.rid.isin(on)]
    print(f"    해당 규칙 신호 {len(z):,}건 (현행 {len(S0[S0.rid.isin(on)]):,}건)")
verdict.log_trials("채널 계좌검증", NT)
print(f"\n시험 {NT}개 기록 · 누적 {verdict.trial_count():,}개")
