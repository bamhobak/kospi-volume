# -*- coding: utf-8 -*-
"""G6·ins≥3 자리 착시(×0.5/×1.5) + 시드 24회 재확인."""
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
exec(rel[rel.index("def sim(S, ds, seed):"):rel.index("ds = [d for d in adates")], globals())
ix = pd.concat([fdr.DataReader("KS11",a,b) for a,b in (("2017-01-01","2019-12-31"),("2020-01-01","2026-09-04"))])
ix = ix[~ix.index.duplicated()].sort_index(); ix = ix[ix.Close>0]; ix["d"] = ix.index.strftime("%Y%m%d")
KP["kdev"] = KP.date.map(dict(zip(ix.d, (ix.Close/ix.Close.rolling(60).mean()-1)*100)))
core = base(KP,30)&(KP.dma60>0)&(KP.fromhi>=-15)&(KP.fw20<1)&(KP.vol20<=3); ins = KP.ins60.fillna(0)
cond = (KP.kdev>6)&core&(ins>=3)
PER = [("전체","20180101","20991231"),("학습","20180101","20221231"),("검증","20230101","20991231"),("붐제외","20180101","20241231")]
def run(R, d0="20180101", d1="20991231", seeds=12):
    S = build(R); ds = [d for d in adates if d0<=d<=d1]; return [sim(S, ds, k) for k in range(seeds)]
def scaled(R,k): return {r:(K,h,s,p*k,m,c) for r,(K,h,s,p,m,c) in R.items()}
print("  G6·ins≥3 자리 착시 (전체 구간)")
for k in (0.5, 1.0, 1.5):
    b = [r["nav"] for r in run(scaled(RULES,k))]; v = [r["nav"] for r in run(scaled({**RULES,"N1":(KP,60,None,4,5,cond)},k))]
    print(f"  ×{k}: {np.median(b):.2f}→{np.median(v):.2f}배({np.mean([a>c for a,c in zip(v,b)])*100:>3.0f}%)")
print("\n  시드 24회 재확인 (4구간)")
for nm, d0, d1 in PER:
    b = [r["nav"] for r in run(RULES, d0, d1, 24)]; v = [r["nav"] for r in run({**RULES,"N1":(KP,60,None,4,5,cond)}, d0, d1, 24)]
    print(f"  {nm:<6} {np.median(b):.2f}→{np.median(v):.2f}배({np.mean([a>c for a,c in zip(v,b)])*100:>3.0f}%)")
