# -*- coding: utf-8 -*-
"""규칙 관계 분석(rules_relation.py)에서 나온 개선 후보 3개를 계좌로 검증한다.

관찰
  · [깊은 이격](P4) 신호의 92% 가 ±5일 안에 [업종붕괴 이탈](P3) 도 뜬다 — 거의 부분집합.
    그런데 빼면 자산이 0.49배 준다 → 독립된 아이디어가 아니라 '같은 아이디어에 자리를 더 준 것'.
  · 하락장 규칙 6개의 월별 동조 상관 0.96 — 사실상 한 덩어리. 진짜 분산은 3개(하락덩어리·P1·P2).
  · [업종붕괴 이탈] 을 빼면 낙폭이 -8.3→-5.8% 로 크게 좋아지지만 자산 1.05배를 잃는다.

실험 (같은 시드 짝지어 · 전체/학습/검증/붐제외)
  A) P4 를 없애고 그 자리를 P3 에 준다 (P3 최대종목 4→8) — 단순화해도 같은가
  B) P3 비중을 3%→2% 로 줄인다 — 낙폭을 사고 자산을 얼마나 내주나
  C) 상승장 규칙 P1·P2 비중을 1.5배 — 유일한 분산 축을 키우면
사용: python rules_improve.py
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
src = (BASE/"portfolio.py").read_text(encoding="utf-8")
ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES = ns["KP"], ns["KQ"], ns["RULES"]
adates = sorted(set(KP.date)|set(KQ.date)); ADI = {d:i for i,d in enumerate(adates)}
rel = (BASE/"rules_relation.py").read_text(encoding="utf-8")
exec(rel[rel.index("def build(R):"):rel.index("S = build(RULES)")], globals())          # build()
exec(rel[rel.index("def sim(S, ds, seed):"):rel.index("ds = [d for d in adates")], globals())  # sim()

def tweak(R, rid, pct=None, mx=None):
    K,h,s,p,m,c = R[rid]; return (K,h,s, pct if pct is not None else p, mx if mx is not None else m, c)
CAND = {
 "현재 9규칙": dict(RULES),
 "A) P4 제거 + P3 자리 4→8": {**{k:v for k,v in RULES.items() if k!="P6"}, "P4": tweak(RULES,"P4",mx=8)},
 "B) P3 비중 3→2%":        {**RULES, "P4": tweak(RULES,"P4",pct=2)},
 "C) P1·P2 비중 ×1.5":     {**RULES, "P7": tweak(RULES,"P7",pct=RULES["P7"][3]*1.5), "P1": tweak(RULES,"P1",pct=RULES["P1"][3]*1.5)},
 "A+C":                    {**{k:v for k,v in RULES.items() if k!="P6"}, "P4": tweak(RULES,"P4",mx=8),
                            "P7": tweak(RULES,"P7",pct=RULES["P7"][3]*1.5), "P1": tweak(RULES,"P1",pct=RULES["P1"][3]*1.5)},
}
PER = [("전체","20180101","20991231"),("학습","20180101","20221231"),("검증","20230101","20991231"),("붐제외","20180101","20241231")]
SEEDS = 12
print(f"  계좌 비교 (시드 {SEEDS}회 · 같은 시드끼리 짝지어 · 괄호는 현재를 이긴 비율)\n")
print(f"  {'구성':<24}" + "".join(f"{p[0]:>17}" for p in PER) + f"{'낙폭':>8}")
REF = None
for nm, R in CAND.items():
    S = build(R); cols = []
    for _, d0, d1 in PER:
        ds = [d for d in adates if d0 <= d <= d1]
        cols.append([sim(S, ds, k) for k in range(SEEDS)])
    if REF is None: REF = cols
    line = ""
    for i, c in enumerate(cols):
        m = np.median([x["nav"] for x in c]); w = np.mean([a["nav"] > b["nav"] for a, b in zip(c, REF[i])])*100
        line += f"{m:>10.2f}배      " if nm == "현재 9규칙" else f"{m:>10.2f}배({w:>3.0f}%)"
    print(f"  {nm:<24}{line}{np.median([x['mdd'] for x in cols[0]]):>7.1f}%")
