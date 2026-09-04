# -*- coding: utf-8 -*-
"""[외인 매집] 게이트를 넓혀 횡보장에도 열면 계좌는 어떻게 되나.
현행 게이트 = 코스피 60일선 위(up60). 후보 = 코스피 60일선 이격 >= -5% (횡보+상승, 하락만 제외) / 게이트 없음.
같은 시드 짝지어 전체·학습·검증·붐제외 + 연도별."""
import io, sys, warnings; warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd, FinanceDataReader as fdr
BASE = Path(__file__).parent
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns); sys.stdout = real
KP, KQ, RULES, base = ns["KP"], ns["KQ"], ns["RULES"], ns["base"]
adates = sorted(set(KP.date)|set(KQ.date)); ADI = {d:i for i,d in enumerate(adates)}
rel = (BASE/"rules_relation.py").read_text(encoding="utf-8")
exec(rel[rel.index("def build(R):"):rel.index("S = build(RULES)")], globals())
simsrc = rel[rel.index("def sim(S, ds, seed):"):rel.index("ds = [d for d in adates")]
exec(simsrc.replace("return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid)",
                    "return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid, curve=Cv)"), globals())
ix = pd.concat([fdr.DataReader("KS11",a,b) for a,b in (("2017-01-01","2019-12-31"),("2020-01-01","2026-09-04"))])
ix = ix[~ix.index.duplicated()].sort_index(); ix = ix[ix.Close>0]; ix["d"] = ix.index.strftime("%Y%m%d")
DEV = dict(zip(ix.d, (ix.Close/ix.Close.rolling(60).mean()-1)*100)); KP["kdev"] = KP.date.map(DEV)
core = (base(KP,30)&(KP["cap조"]>=1)&(KP["cap조"]<10)&(KP.fw20>=1)&(KP.ow60<0.4)&(KP.r16>=100)&(KP.r16<150)
        &(KP.fromhi>=-15)&(KP.fromlo>=70)&(KP.ins60.fillna(0)>0))
K,h,s,p,m,_ = RULES["P7"]
CAND = {"현행 (60일선 위)": dict(RULES),
        "이격 ≥ -5% (횡보도 연다)": {**RULES, "P7": (K,h,s,p,m, core&(KP.kdev>=-5))},
        "이격 ≥ -3%": {**RULES, "P7": (K,h,s,p,m, core&(KP.kdev>=-3))},
        "게이트 없음": {**RULES, "P7": (K,h,s,p,m, core)}}
PER = [("전체","20180101","20991231"),("학습","20180101","20221231"),("검증","20230101","20991231"),("붐제외","20180101","20241231")]
SEEDS = 12; REF = None; CURVES = {}
print(f"  계좌 비교 (시드 {SEEDS}회 · 같은 시드끼리 짝지어 · 괄호는 현행을 이긴 비율)\n")
print(f"  {'P7 게이트':<22}" + "".join(f"{q[0]:>17}" for q in PER) + f"{'낙폭':>8}{'P7체결':>7}")
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
    n7 = np.median([sum(1 for _ in []) for _ in [0]])
    print(f"  {nm:<22}{line}{np.median([x['mdd'] for x in cols[0]]):>7.1f}%{int(len(S[S.rid=='P7'])):>7}")
ds = [d for d in adates if d >= "20180101"]; yrs = np.array([d[:4] for d in ds]); b0 = CURVES["현행 (60일선 위)"]
print("\n  연도별 (현행 대비 · 같은 시드에서 이긴 비율)")
print(f"  {'연도':<6}{'현행':>8}" + "".join(f"{n[:10]:>20}" for n in list(CURVES)[1:]))
for y in sorted(set(yrs)):
    idx = np.where(yrs==y)[0]; i0 = max(idx[0]-1,0); i1 = idx[-1]
    ref = np.array([(c[i1]/c[i0]-1)*100 for c in b0]); line = f"  {y:<6}{np.median(ref):>+7.1f}%"
    for nm in list(CURVES)[1:]:
        v = np.array([(c[i1]/c[i0]-1)*100 for c in CURVES[nm]]); line += f"{np.median(v):>+12.1f}% ({np.mean(v>ref)*100:>3.0f}%)"
    print(line)
