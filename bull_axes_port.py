# -*- coding: utf-8 -*-
"""세 번째 상승장 축을 10번째 규칙으로 얹었을 때 계좌 — 같은 시드 짝지어 4구간 + 연도별.
N1 내부자 축: 코스피 이격>+5 · ins60≥2 · 60일선 위 · 고점-15% · 외인20일<1 · 변동성≤3 · 60일 보유 · 비중 4% · 최대 5
N2 기관 축:   코스피 이격>+5 · 기관20일≥1 · 외인20일≥0 · 60일선 위 · 고점-10% · 60일 · 4% · 5"""
import io, sys, warnings; warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd, FinanceDataReader as fdr
BASE = Path(__file__).parent
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns); sys.stdout = real
KP, KQ, RULES, base = ns["KP"], ns["KQ"], ns["RULES"], ns["base"]
for c in ("dma60","vol20","fromhi","fw20","ow20","ins60"): assert c in KP.columns, c
adates = sorted(set(KP.date)|set(KQ.date)); ADI = {d:i for i,d in enumerate(adates)}
rel = (BASE/"rules_relation.py").read_text(encoding="utf-8")
exec(rel[rel.index("def build(R):"):rel.index("S = build(RULES)")], globals())
exec(rel[rel.index("def sim(S, ds, seed):"):rel.index("ds = [d for d in adates")].replace(
     "return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid)", "return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid, curve=Cv)"), globals())
ix = pd.concat([fdr.DataReader("KS11",a,b) for a,b in (("2017-01-01","2019-12-31"),("2020-01-01","2026-09-04"))])
ix = ix[~ix.index.duplicated()].sort_index(); ix = ix[ix.Close>0]; ix["d"] = ix.index.strftime("%Y%m%d")
KP["kdev"] = KP.date.map(dict(zip(ix.d, (ix.Close/ix.Close.rolling(60).mean()-1)*100)))
G5 = KP.kdev>5
N1 = base(KP,30)&G5&(KP.ins60.fillna(0)>=2)&(KP.dma60>0)&(KP.fromhi>=-15)&(KP.fw20<1)&(KP.vol20<=3)
N2 = base(KP,30)&G5&(KP.ow20>=1)&(KP.fw20>=0)&(KP.dma60>0)&(KP.fromhi>=-10)
CAND = {"현재 9규칙": dict(RULES),
        "+N1 내부자 축": {**RULES, "N1": (KP,60,None,4,5,N1)},
        "+N2 기관 축":   {**RULES, "N2": (KP,60,None,4,5,N2)},
        "+N1+N2":       {**RULES, "N1": (KP,60,None,4,5,N1), "N2": (KP,60,None,4,5,N2)},
        "+N1 (비중 2%·최대 3)": {**RULES, "N1": (KP,60,None,2,3,N1)}}
PER = [("전체","20180101","20991231"),("학습","20180101","20221231"),("검증","20230101","20991231"),("붐제외","20180101","20241231")]
SEEDS = 12; REF = None; CURVES = {}; DIRECT = {}
print(f"  계좌 비교 (시드 {SEEDS}회 · 같은 시드끼리 짝지어 · 괄호는 현재를 이긴 비율)\n")
print(f"  {'구성':<22}" + "".join(f"{q[0]:>17}" for q in PER) + f"{'낙폭':>8}{'새규칙 체결':>10}{'직접기여':>9}")
for nm, R in CAND.items():
    S = build(R); cols = []
    for _, d0, d1 in PER:
        ds = [d for d in adates if d0 <= d <= d1]; cols.append([sim(S, ds, k) for k in range(SEEDS)])
    if REF is None: REF = cols
    CURVES[nm] = [r["curve"].to_numpy() for r in cols[0]]
    line = ""
    for i, c in enumerate(cols):
        mnav = np.median([x["nav"] for x in c]); w = np.mean([a["nav"]>b["nav"] for a,b in zip(c, REF[i])])*100
        line += f"{mnav:>10.2f}배      " if REF is cols else f"{mnav:>10.2f}배({w:>3.0f}%)"
    new = [k for k in R if k.startswith("N")]
    direct = np.median([sum(x["byrid"].get(k,0) for k in new) for x in cols[0]]) if new else 0
    nfill = int(len(S[S.rid.isin(new)])) if new else 0
    print(f"  {nm:<22}{line}{np.median([x['mdd'] for x in cols[0]]):>7.1f}%{nfill:>10}{direct:>+9.2f}")
ds = [d for d in adates if d >= "20180101"]; yrs = np.array([d[:4] for d in ds]); b0 = CURVES["현재 9규칙"]
print("\n  연도별 (현재 대비 · 같은 시드에서 이긴 비율)")
print(f"  {'연도':<6}{'현재':>8}" + "".join(f"{n[:12]:>20}" for n in list(CURVES)[1:]))
for y in sorted(set(yrs)):
    idx = np.where(yrs==y)[0]; i0 = max(idx[0]-1,0); i1 = idx[-1]
    ref = np.array([(c[i1]/c[i0]-1)*100 for c in b0]); line = f"  {y:<6}{np.median(ref):>+7.1f}%"
    for nm in list(CURVES)[1:]:
        v = np.array([(c[i1]/c[i0]-1)*100 for c in CURVES[nm]]); line += f"{np.median(v):>+12.1f}% ({np.mean(v>ref)*100:>3.0f}%)"
    print(line)
