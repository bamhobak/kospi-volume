# -*- coding: utf-8 -*-
"""N1(내부자 축) 자리 제한 착시 점검 — 전 규칙 비중을 ×0.5(자리 여유)·×1.5(자리 빡빡)로 바꿔도 이득이 유지되는가."""
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
N1 = base(KP,30)&(KP.kdev>5)&(KP.ins60.fillna(0)>=2)&(KP.dma60>0)&(KP.fromhi>=-15)&(KP.fw20<1)&(KP.vol20<=3)
def scaled(R, k): return {r:(K,h,s,p*k,m,c) for r,(K,h,s,p,m,c) in R.items()}
PER = [("전체","20180101","20991231"),("학습","20180101","20221231"),("검증","20230101","20991231"),("붐제외","20180101","20241231")]
SEEDS = 12
print(f"  자리 제한 착시 점검 · 시드 {SEEDS}회 짝지어 · 괄호는 같은 비중의 현재를 이긴 비율\n")
print(f"  {'구성':<26}" + "".join(f"{q[0]:>17}" for q in PER) + f"{'낙폭':>8}")
for k, kn in ((0.5,"비중 ×0.5 (자리 여유)"), (1.0,"비중 ×1.0 (현재)"), (1.5,"비중 ×1.5 (자리 빡빡)")):
    ref = None
    for nm, R in ((f"{kn} 현재", scaled(RULES,k)), (f"{kn} +N1", scaled({**RULES,"N1":(KP,60,None,4,5,N1)},k))):
        S = build(R); cols = []
        for _, d0, d1 in PER:
            ds = [d for d in adates if d0 <= d <= d1]; cols.append([sim(S, ds, s) for s in range(SEEDS)])
        if ref is None: ref = cols
        line = ""
        for i, c in enumerate(cols):
            mnav = np.median([x["nav"] for x in c]); w = np.mean([a["nav"]>b["nav"] for a,b in zip(c, ref[i])])*100
            line += f"{mnav:>10.2f}배      " if ref is cols else f"{mnav:>10.2f}배({w:>3.0f}%)"
        print(f"  {nm:<26}{line}{np.median([x['mdd'] for x in cols[0]]):>7.1f}%")
    print()
