# -*- coding: utf-8 -*-
"""규칙 하나만으로 1억을 굴렸을 때 — 연도별 손익과 '최고 해를 뺀' 누적.

사용자 요청(2026-09-06): 각 규칙 단독 · 원금 1억 · 연도별 벌고 잃은 금액 · 규칙마다 가장 많이 번 해는
빼고 · 첫해부터 누적. 최고 해를 빼는 건 '한 해 몰빵' 착시(2020년 등)를 걷어내 평소 실력을 보려는 것.
가정: 종목당 투입 = 100% ÷ 최대 보유 종목 수(mx) → 자리가 다 차면 1억 전부 투입. 청산 연도 기준 실현손익.
     복리(계좌가 불어나면 다음 거래도 커짐). 시드 12개 중앙값.
사용: IX_FROM=2004-06-01 DART_FROM=20040101 PANEL_KP=panel_kp.pkl PANEL_KQ=panel_kq.pkl python solo_cum.py
"""
import io, os, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent; SEEDS = 12; CAP = 1_0000_0000
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES = ns["KP"], ns["KQ"], ns["RULES"]
adates = sorted(set(KP.date) | set(KQ.date)); ADI = {d: i for i, d in enumerate(adates)}
rel = (BASE/"rules_relation.py").read_text(encoding="utf-8")
exec(rel[rel.index("def build(R):"):rel.index("S = build(RULES)")], globals())
cm = (BASE/"cmp_money.py").read_text(encoding="utf-8")
exec("def sim(S, ds, seed):" + cm.split("def sim(S, ds, seed):")[1].split("def variant")[0], globals())
NAME = {"P7":"외인 매집","P1":"조용한 신고가","P4":"업종붕괴 이탈","P6":"깊은 이격","P3":"폭락반등",
        "P2":"조정매집","D1":"낙폭과대","D2":"저PBR 낙폭","P5":"자사주 낙폭"}
ORDER = ["P7","P1","P2","P3","P4","P6","P5","D1","D2"]
ds = [d for d in adates if d >= "20050101"]; YRS = [str(y) for y in range(2005, 2027)]
res = {}
for rid in ORDER:
    P, h, stop, pct, mx, cond = RULES[rid]
    S = build({rid: (P, h, stop, 100.0/mx, mx, cond)})
    logs = [sim(S, ds, k) for k in range(SEEDS)]
    yr = {y: np.median([L[L.y == y].gain.sum() for L in logs])*CAP for y in YRS}
    res[rid] = yr
    print(f"  {NAME[rid]} 완료", file=sys.stderr, flush=True)
pd.DataFrame(res).rename(columns=NAME).to_csv(BASE/"data"/"solo_yearly.csv")

# 표: 행=연도, 열=규칙, 셀=누적(최고 해 제외). 최고 해 셀은 ✕ 표시.
best = {rid: max(res[rid], key=lambda y: res[rid][y]) for rid in ORDER}
W = 11
print("규칙 단독 · 원금 1억 · 최고 해 제외 누적 손익(만원)  [✕ = 그 규칙의 최고 해, 누적에서 뺌]")
print(f"{'연도':<6}" + "".join(f"{NAME[r]:>{W}}" for r in ORDER))
print("-"*(6+W*len(ORDER)))
cum = {r: 0.0 for r in ORDER}
for y in YRS:
    row = f"{y:<6}"
    for r in ORDER:
        v = res[r][y]
        if y == best[r]: row += f"{'✕':>{W}}"
        elif abs(v) < 1: row += f"{'·':>{W}}"
        else:
            cum[r] += v; row += f"{cum[r]/1e4:>+{W},.0f}"
    print(row)
print("-"*(6+W*len(ORDER)))
print(f"{'누적':<6}" + "".join(f"{cum[r]/1e4:>+{W},.0f}" for r in ORDER))
print(f"{'뺀 해':<6}" + "".join(f"{best[r]:>{W}}" for r in ORDER))
print(f"{'그해액':<6}" + "".join(f"{res[r][best[r]]/1e4:>+{W},.0f}" for r in ORDER))
print(f"{'포함시':<6}" + "".join(f"{(cum[r]+res[r][best[r]])/1e4:>+{W},.0f}" for r in ORDER))
print("\n연도별 손익(만원, 누적 아님)")
print(f"{'연도':<6}" + "".join(f"{NAME[r]:>{W}}" for r in ORDER))
for y in YRS:
    if all(abs(res[r][y]) < 1 for r in ORDER): continue
    print(f"{y:<6}" + "".join(f"{res[r][y]/1e4:>+{W},.0f}" if abs(res[r][y]) >= 1 else f"{'·':>{W}}" for r in ORDER))
