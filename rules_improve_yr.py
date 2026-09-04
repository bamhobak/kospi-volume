# -*- coding: utf-8 -*-
"""개선 후보의 연도별 짝비교 — 특정 해에만 기댄 결과인지 본다(연도 쏠림 함정)."""
import io, sys, warnings; warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns); sys.stdout = real
KP, KQ, RULES = ns["KP"], ns["KQ"], ns["RULES"]
adates = sorted(set(KP.date)|set(KQ.date)); ADI = {d:i for i,d in enumerate(adates)}
rel = (BASE/"rules_relation.py").read_text(encoding="utf-8")
exec(rel[rel.index("def build(R):"):rel.index("S = build(RULES)")], globals())
simsrc = rel[rel.index("def sim(S, ds, seed):"):rel.index("ds = [d for d in adates")]
exec(simsrc.replace("return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid)",
                    "return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid, curve=Cv)"), globals())
imp = (BASE/"rules_improve.py").read_text(encoding="utf-8")
exec(imp[imp.index("def tweak(R"):imp.index("PER = [")], globals())     # tweak(), CAND
ds = [d for d in adates if d >= "20180101"]; yrs = np.array([d[:4] for d in ds]); SEEDS = 12
res = {}
for nm in ("현재 9규칙", "A) P4 제거 + P3 자리 4→8", "C) P1·P2 비중 ×1.5", "A+C"):
    S = build(CAND[nm]); runs = [sim(S, ds, k)["curve"].to_numpy() for k in range(SEEDS)]
    Y = {}
    for y in sorted(set(yrs)):
        idx = np.where(yrs == y)[0]; i0 = max(idx[0]-1, 0); i1 = idx[-1]
        Y[y] = np.array([(c[i1]/c[i0]-1)*100 for c in runs])
    res[nm] = Y
print(f"  연도별 수익률(%) · 시드 {SEEDS}회 중앙값 · 괄호는 같은 시드에서 현재를 이긴 비율\n")
print(f"  {'연도':<6}{'현재':>8}" + "".join(f"{n[:12]:>22}" for n in list(res)[1:]))
base = res["현재 9규칙"]
for y in sorted(base):
    line = f"  {y:<6}{np.median(base[y]):>+7.1f}%"
    for nm in list(res)[1:]:
        v = res[nm][y]; w = np.mean(v > base[y])*100
        line += f"{np.median(v):>+12.1f}% ({w:>3.0f}%)"
    print(line)
print("\n  이긴 해 수 (중앙값 기준):")
for nm in list(res)[1:]:
    won = sum(np.median(res[nm][y]) > np.median(base[y]) for y in base)
    print(f"    {nm:<26} {won}/{len(base)}년")
