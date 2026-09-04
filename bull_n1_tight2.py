# -*- coding: utf-8 -*-
"""게이트 +6 중간 후보를 계좌·연도별로 — 그리고 상위 후보 자리 착시(×0.5/×1.5)."""
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
exec(rel[rel.index("def sim(S, ds, seed):"):rel.index("ds = [d for d in adates")].replace(
     "return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid)", "return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid, curve=Cv)"), globals())
ix = pd.concat([fdr.DataReader("KS11",a,b) for a,b in (("2017-01-01","2019-12-31"),("2020-01-01","2026-09-04"))])
ix = ix[~ix.index.duplicated()].sort_index(); ix = ix[ix.Close>0]; ix["d"] = ix.index.strftime("%Y%m%d")
KP["kdev"] = KP.date.map(dict(zip(ix.d, (ix.Close/ix.Close.rolling(60).mean()-1)*100)))
core = base(KP,30)&(KP.dma60>0)&(KP.fromhi>=-15)&(KP.fw20<1)&(KP.vol20<=3); ins = KP.ins60.fillna(0)
V = {"N1 원안 G5·ins≥2": (KP.kdev>5)&core&(ins>=2), "G6·ins≥2": (KP.kdev>6)&core&(ins>=2),
     "G6·ins≥3": (KP.kdev>6)&core&(ins>=3), "G7·ins≥2": (KP.kdev>7)&core&(ins>=2), "V6 G8·ins≥3": (KP.kdev>8)&core&(ins>=3)}
PER = [("전체","20180101","20991231"),("학습","20180101","20221231"),("검증","20230101","20991231"),("붐제외","20180101","20241231")]
SEEDS = 12; ds_all = [d for d in adates if d >= "20180101"]; yrs = np.array([d[:4] for d in ds_all])
def run(R, d0="20180101", d1="20991231"):
    S = build(R); ds = [d for d in adates if d0<=d<=d1]; return [sim(S, ds, k) for k in range(SEEDS)]
def yr_ret(runs):
    out = {}
    for y in sorted(set(yrs)):
        idx = np.where(yrs==y)[0]; i0 = max(idx[0]-1,0); i1 = idx[-1]
        out[y] = np.array([(r["curve"].to_numpy()[i1]/r["curve"].to_numpy()[i0]-1)*100 for r in runs])
    return out
B = {p[0]: run(RULES, p[1], p[2]) for p in PER}; BY = yr_ret(B["전체"])
print(f"  {'후보':<18}{'전체':>12}{'학습':>12}{'검증':>12}{'붐제외':>12}{'낙폭':>7}{'이김':>4}{'짐':>3}  연도별")
for nm, cond in V.items():
    R = {**RULES, "N1": (KP,60,None,4,5,cond)}; cells = ""; res = {}
    for p in PER:
        res[p[0]] = run(R, p[1], p[2]); v = [r["nav"] for r in res[p[0]]]
        cells += f"{np.median(v):>7.2f}({np.mean([a>b['nav'] for a,b in zip(v,B[p[0]])])*100:>3.0f}%)"
    Y = yr_ret(res["전체"]); won=lost=0; ys=""
    for y in sorted(Y):
        dm = np.median(Y[y])-np.median(BY[y])
        if abs(dm)<0.05: ys += f" {y[2:]}:="; continue
        won += dm>0; lost += dm<0; ys += f" {y[2:]}:{np.mean(Y[y]>BY[y])*100:>3.0f}%"
    print(f"  {nm:<18}{cells}{np.median([r['mdd'] for r in res['전체']]):>6.1f}%{won:>4}{lost:>3} {ys}")
print("\n  ── 자리 착시 (전 규칙 비중 ×0.5 / ×1.5 · 전체 구간) ──")
def scaled(R,k): return {r:(K,h,s,p*k,m,c) for r,(K,h,s,p,m,c) in R.items()}
for nm in ("G6·ins≥2", "V6 G8·ins≥3", "N1 원안 G5·ins≥2"):
    line = f"  {nm:<18}"
    for k in (0.5, 1.5):
        b = [r["nav"] for r in run(scaled(RULES,k))]; v = [r["nav"] for r in run(scaled({**RULES,"N1":(KP,60,None,4,5,V[nm])},k))]
        line += f"  ×{k}: {np.median(b):.2f}→{np.median(v):.2f}배({np.mean([a>c for a,c in zip(v,b)])*100:>3.0f}%)"
    print(line)
