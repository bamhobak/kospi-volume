# -*- coding: utf-8 -*-
"""N1 조이기 — 이기는 해를 늘린다. 변형 8종을 계좌·연도별로 짝지어 비교."""
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
core = base(KP,30)&(KP.dma60>0)&(KP.fromhi>=-15)&(KP.fw20<1)&(KP.vol20<=3)
ins = KP.ins60.fillna(0)
V = {
 "N1 원안 (G5·ins≥2·자리5)":      ((KP.kdev>5)&core&(ins>=2), 4, 5),
 "V1 게이트 +8":                 ((KP.kdev>8)&core&(ins>=2), 4, 5),
 "V2 내부자 ≥3":                 ((KP.kdev>5)&core&(ins>=3), 4, 5),
 "V3 +거래량 침체 r16<120":        ((KP.kdev>5)&core&(ins>=2)&(KP.r16<120), 4, 5),
 "V4 +저점 대비 +50%":            ((KP.kdev>5)&core&(ins>=2)&(KP.fromlo>=50), 4, 5),
 "V5 자리 5→3":                  ((KP.kdev>5)&core&(ins>=2), 4, 3),
 "V6 게이트 +8 · 내부자 ≥3":        ((KP.kdev>8)&core&(ins>=3), 4, 5),
 "V7 내부자 ≥3 · 침체 · 자리 3":     ((KP.kdev>5)&core&(ins>=3)&(KP.r16<120), 4, 3),
 "V8 게이트 +8 · 자리 3":          ((KP.kdev>8)&core&(ins>=2), 4, 3),
}
PER = [("전체","20180101","20991231"),("학습","20180101","20221231"),("검증","20230101","20991231"),("붐제외","20180101","20241231")]
SEEDS = 12; ds_all = [d for d in adates if d >= "20180101"]; yrs = np.array([d[:4] for d in ds_all])
S0 = build(RULES); base_runs = [sim(S0, ds_all, k) for k in range(SEEDS)]
REF = {p[0]: [sim(S0, [d for d in adates if p[1]<=d<=p[2]], k)["nav"] for k in range(SEEDS)] for p in PER[1:]}
REF["전체"] = [r["nav"] for r in base_runs]; b0 = [r["curve"].to_numpy() for r in base_runs]
def yr_ret(curves):
    out = {}
    for y in sorted(set(yrs)):
        idx = np.where(yrs==y)[0]; i0 = max(idx[0]-1,0); i1 = idx[-1]
        out[y] = np.array([(c[i1]/c[i0]-1)*100 for c in curves])
    return out
BY = yr_ret(b0)
print(f"  {'변형':<28}{'전체':>12}{'학습':>12}{'검증':>12}{'붐제외':>12}{'낙폭':>7}{'이긴해':>7}{'진해':>5}  연도별(현재 대비 이긴 비율)")
rows = []
for nm, (cond, pct, mx) in V.items():
    R = {**RULES, "N1": (KP,60,None,pct,mx,cond)}; S = build(R)
    runs = [sim(S, ds_all, k) for k in range(SEEDS)]
    cells = ""; navs = {}
    for p in PER:
        v = [r["nav"] for r in runs] if p[0]=="전체" else [sim(S, [d for d in adates if p[1]<=d<=p[2]], k)["nav"] for k in range(SEEDS)]
        w = np.mean([a>b for a,b in zip(v, REF[p[0]])])*100; navs[p[0]] = np.median(v)
        cells += f"{np.median(v):>7.2f}({w:>3.0f}%)"
    Y = yr_ret([r["curve"].to_numpy() for r in runs])
    won = lost = 0; ystr = ""
    for y in sorted(Y):
        w = np.mean(Y[y] > BY[y])*100; dm = np.median(Y[y]) - np.median(BY[y])
        if abs(dm) < 0.05: ystr += f" {y[2:]}:="; continue
        won += dm > 0; lost += dm < 0; ystr += f" {y[2:]}:{w:>3.0f}%"
    mdd = np.median([r["mdd"] for r in runs])
    print(f"  {nm:<28}{cells}{mdd:>6.1f}%{won:>6}{lost:>5}  {ystr}")
    rows.append((nm, won, lost, navs["전체"], mdd))
print("\n  ── 이긴 해 많은 순 ──")
for nm, w, l, nav, mdd in sorted(rows, key=lambda x: (-x[1], x[2], -x[3])):
    print(f"    {nm:<28} 이김 {w} · 짐 {l} · 전체 {nav:.2f}배 · 낙폭 {mdd:.1f}%")
