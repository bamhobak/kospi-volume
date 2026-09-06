# -*- coding: utf-8 -*-
"""9규칙 계좌 시뮬을 2005년부터 돌린다 — 규칙 단위가 아니라 '돈' 으로 본다.

왜: 규칙 단위로는 [폭락반등] 이 2008년에 -4.0% 로 졌다(2026-09-06 실측). 그런데 아홉 규칙이
    함께 돌면 다른 규칙이 그 자리를 메울 수 있다. 계좌 수준에서 같은 결론이 나오는지 본다.

⚠ 반드시 아래 환경변수와 함께 돌릴 것 — 안 그러면 과거 구간이 통째로 0건이 된다.
    IX_FROM=2004-06-01  국면 판정 지수 시작(기본 2017 이면 그 이전이 '국면 모름')
    DART_FROM=20040101  자사주 공시 시작(기본 20180101)
    PANEL_KP=panel_kp.pkl PANEL_KQ=panel_kq.pkl
사용: (위 환경변수) python hist_portfolio.py [--seeds 12]
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
NAME = {"P7":"외인 매집","P1":"조용한 신고가","P4":"업종붕괴 이탈","P6":"깊은 이격","P3":"폭락반등",
        "P2":"조정매집","D1":"낙폭과대","D2":"저PBR 낙폭","P5":"자사주 낙폭"}

S = build(RULES)
print(f"패널 {os.environ.get('PANEL_KP','kp_ow.pkl')} / {os.environ.get('PANEL_KQ','kq_ow.pkl')} · "
      f"거래일 {adates[0]}~{adates[-1]} · 신호 {len(S):,}건 · 시드 {SEEDS}회")
print("  규칙별 신호: " + " ".join(f"{NAME[k]} {v}" for k, v in S.rid.value_counts().items()))

PER = [("2005~2007","20050101","20071231"), ("2008~2009 위기","20080101","20091231"),
       ("2010~2012","20100101","20121231"), ("2013~2017","20130101","20171231"),
       ("2018~2022","20180101","20221231"), ("2023~2026","20230101","20991231"),
       ("전체 2005~","20050101","20991231")]
print(f"\n{'구간':<16}{'연수':>5}{'자산':>9}{'연복리':>9}{'최대낙폭':>10}{'거래':>7}  규칙별 기여(상위 3)")
print("-"*104)
for nm, lo, hi in PER:
    ds = [d for d in adates if lo <= d <= hi]
    if len(ds) < 60: print(f"{nm:<16} (거래일 부족)"); continue
    R = [sim(S, ds, k) for k in range(SEEDS)]
    nav = np.median([r["nav"] for r in R]); mdd = np.median([r["mdd"] for r in R])
    yrs = len(ds)/246
    cagr = (nav**(1/yrs)-1)*100 if nav > 0 else float("nan")
    ntr = int(np.median([sum(1 for _ in r["byrid"]) for r in R]))
    agg = {}
    for r in R:
        for k, v in r["byrid"].items(): agg[k] = agg.get(k, 0)+v/SEEDS
    top = " · ".join(f"{NAME[k]} {v*100:+.0f}" for k, v in sorted(agg.items(), key=lambda x: -x[1])[:3])
    nsig = int(((S.date >= lo) & (S.date <= hi)).sum())
    print(f"{nm:<16}{yrs:>5.1f}{nav:>8.2f}배{cagr:>8.1f}%{mdd:>9.1f}%{nsig:>7}  {top}")

# 연도별 — 어느 해에 벌고 어느 해에 잃었나
ds_all = [d for d in adates if d >= "20050101"]
RA = [sim(S, ds_all, k) for k in range(SEEDS)]
yrs = np.array([d[:4] for d in ds_all])
print(f"\n연도별 계좌 수익률(중앙값)")
out = []
for y in sorted(set(yrs)):
    idx = np.where(yrs == y)[0]; i0 = max(idx[0]-1, 0); i1 = idx[-1]
    v = [(r["curve"].to_numpy()[i1]/r["curve"].to_numpy()[i0]-1)*100 for r in RA]
    out.append(f"{y}:{np.median(v):+.1f}%")
print("  " + " · ".join(out))
