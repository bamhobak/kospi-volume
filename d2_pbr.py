# -*- coding: utf-8 -*-
"""[저PBR 낙폭] PBR 문턱 완화 검토 — 0.5 → 0.8 로 넓히면 계좌가 나아지나.

정밀 점검(d2_deep.py)에서 나온 것: 문턱을 완화하면 평균은 낮아지지만 신호가 2.5배로 늘고
신뢰구간 하한이 +6.73 → +8.91 로 올라간다. 2020-03 한 달이 전체 수익의 86% 를 차지하는
쏠림도 희석될 수 있다. 규칙 단위로 좋아 보여도 계좌에서 자리를 뺏으면 손해이므로 끝까지 본다.
  ① 연도 쏠림이 실제로 줄어드는가 ② 계좌 짝 비교(시드 12) ③ 비중 배율 착시 검사
"""
import io, os, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent; SEEDS = 12
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES, TRAIL, base, dn60 = ns["KP"], ns["KQ"], ns["RULES"], ns["TRAIL"], ns["base"], ns["dn60"]
K, hold, stop, pct, mx, cond = RULES["D2"]
core = base(KQ,5)&dn60(KQ)&(KQ.ret20<=-10)&(KQ.su1>=2)&(KQ.u<=-10)&(KQ.ow20>=0)&(KQ.srd==True)
def take(c, h=hold):
    m = c.fillna(False); X = K[m].dropna(subset=[f"n{h}"]).copy()
    di = {x:i for i,x in enumerate(sorted(K.date.unique()))}
    X["di"] = X.date.map(di); X = X.sort_values("di"); keep, last = [], {}
    for t,i,ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t,-10**9) >= i: continue
        last[t] = i+h; keep.append(ix)
    return X.loc[keep].assign(r=lambda d: d[f"n{h}"], y=lambda d: d.date.str[:4])
print("① 연도 쏠림 — 문턱을 넓히면 2020년 비중이 줄어드는가")
for lab, th in (("현행 ≤0.5", 0.5), ("완화 ≤0.8", 0.8), ("완화 ≤1.0", 1.0)):
    z = take(core & (KQ.PBR>0) & (KQ.PBR<=th)); z = z[z.date>="20160101"]
    g = z.groupby("y").r.agg(["size","mean"])
    sh20 = z[z.y=="2020"].r.sum()/z.r.sum()*100 if z.r.sum() else 0
    n20 = int(g.loc["2020","size"]) if "2020" in g.index else 0
    print(f"  {lab:<10}{len(z):>4}건 · 2020년 {n20:>3}건({n20/len(z)*100:>3.0f}%) · "
          f"수익 합 중 2020 비중 {sh20:>3.0f}% · 신호 난 해 {len(g)}개 · "
          + " ".join(f"{i}:{int(r['size'])}" for i, r in g.iterrows()))
adates = sorted(set(KP.date) | set(KQ.date)); ADI = {d: i for i, d in enumerate(adates)}
rel = (BASE/"rules_relation.py").read_text(encoding="utf-8")
exec(rel[rel.index("def build(R):"):rel.index("S = build(RULES)")], globals())
ta = (BASE/"trail_acct.py").read_text(encoding="utf-8")
exec(ta[ta.index("def build2(trail):"):ta.index("PER = [")].replace(
     "def build2(trail):", "def build2(trail, d2cond=None, scale=1.0):").replace(
     "for rid, (K, hold, stop, pct, mx, cond) in RULES.items():",
     "for rid, (K, hold, stop, pct, mx, cond) in RULES.items():\n"
     "        if rid == 'D2' and d2cond is not None: cond = d2cond\n"
     "        pct = min(pct*scale, 100.0/mx)"), globals())
PER = [("학습 2016~22","20160101","20221231"), ("검증 2023~26","20230101","20991231"),
       ("기준 2016~","20160101","20991231")]
VAR = [("현행 PBR≤0.5", None)] + [(f"PBR≤{t}", core & (KQ.PBR>0) & (KQ.PBR<=t)) for t in (0.6, 0.8, 1.0)]
print(f"\n② 계좌 짝 비교 (시드 {SEEDS})")
print(f"  {'안':<16}" + "".join(f"{p[0]:>26}" for p in PER))
print(f"  {'':<16}" + "".join(f"{'자산':>10}{'낙폭':>8}{'시드승':>8}" for p in PER))
BASE_N = {}
for nm, c in VAR:
    S = build2(TRAIL, c); row = ""
    for pn, lo, hi in PER:
        ds = [d for d in adates if lo <= d <= hi]
        R = [sim(S, ds, k) for k in range(SEEDS)]
        nav = [x[0] for x in R]; mdd = np.median([x[1] for x in R])
        if c is None: BASE_N[pn] = nav; w = "기준"
        else: w = f"{sum(a>b for a,b in zip(nav, BASE_N[pn]))}/{SEEDS}"
        row += f"{np.median(nav):>9.2f}배{mdd:>7.0f}%{w:>8}"
    print(f"  {nm:<16}{row}")
print("\n③ 비중 배율을 바꿔도 순서가 유지되나 (기준 2016~)")
ds = [d for d in adates if d >= "20160101"]
for sc in (0.5, 1.5):
    A = [sim(build2(TRAIL, None, sc), ds, k)[0] for k in range(SEEDS)]
    B = [sim(build2(TRAIL, core & (KQ.PBR>0) & (KQ.PBR<=0.8), sc), ds, k)[0] for k in range(SEEDS)]
    print(f"  x{sc}: 현행 {np.median(A):.2f}배 → PBR≤0.8 {np.median(B):.2f}배 · 나은 시드 {sum(b>a for a,b in zip(A,B))}/{SEEDS}")
