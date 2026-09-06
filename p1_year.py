# -*- coding: utf-8 -*-
"""[조용한 신고가] 연도별 성적 — 승률·수익률·수익금, 그리고 재료가 있었는지.

이 규칙만 아홉 중 유일하게 국면 조건이 없고, 21년으로 늘려 보면 2009~2013 내내 졌다.
그런데 판정 전에 확인할 게 있다 — 이 규칙은 신용잔고비(r16)·주간거래대금(rw1)·외국인(fw5)을
쓰는데 과거 패널에 그 값이 없는 해는 신호가 아예 0건이 된다. '졌다' 와 '못 쟀다' 를 구분해야 한다.
사용: IX_FROM=2004-06-01 DART_FROM=20040101 PANEL_KP=panel_kp.pkl PANEL_KQ=panel_kq.pkl python p1_year.py
"""
import io, os, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent; SEEDS = 12; CAPITAL = 1_0000_0000
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES = ns["KP"], ns["KQ"], ns["RULES"]
adates = sorted(set(KP.date) | set(KQ.date)); ADI = {d: i for i, d in enumerate(adates)}
rel = (BASE/"rules_relation.py").read_text(encoding="utf-8")
exec(rel[rel.index("def build(R):"):rel.index("S = build(RULES)")], globals())
exec((BASE/"cmp_money.py").read_text(encoding="utf-8")
     .split("def sim(S, ds, seed):")[1].split("def variant")[0].join(["def sim(S, ds, seed):", ""]),
     globals())
YRS = [str(y) for y in range(2005, 2027)]

# ① 규칙 단위 (자리 제한 없이, 신호 전부)
_, HOLD, STOP, _, _, COND = RULES["P1"]
g = KP.groupby("ticker", sort=False)
low = pd.concat([g.low.shift(-i) for i in range(HOLD)], axis=1).min(axis=1)
r = np.where((low <= KP.buy*(1-STOP)).fillna(False), -STOP*100 - KP.cost, KP[f"n{HOLD}"])
m = COND.fillna(False); X = KP[m].copy(); X["_r"] = r[m.values]; X = X.dropna(subset=["_r"])
di = {x: i for i, x in enumerate(sorted(KP.date.unique()))}
X["di"] = X.date.map(di); X = X.sort_values("di")
keep, last = [], {}
for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
    if last.get(t, -10**9) >= i: continue
    last[t] = i+HOLD; keep.append(ix)
Z = X.loc[keep].assign(y=lambda d: d.date.str[:4])

# ② 계좌 안 수익금 (9규칙 동시 · 시드 12 중앙값)
S = build(RULES); ds = [d for d in adates if d >= "20050101"]
LOG = [sim(S, ds, k) for k in range(SEEDS)]

# ③ 재료가 그 해에 있었나 — 조건별 통과 종목·일 수
NEED = {"r16": "신용잔고비", "rw1": "주간거래대금", "fw5": "외국인5일", "sr20": "업종20일"}
KP["_y"] = KP.date.str[:4]
have = {c: KP.groupby("_y")[c].apply(lambda s: s.notna().mean()*100) for c in NEED}

print("[조용한 신고가]  40일 보유 · 손절 -15% · 종목당 12% · 최대 7종목 · 원금 1억")
print(f"  {'해':<6}{'건수':>6}{'승률':>7}{'평균':>8}{'중앙':>8}{'계좌건수':>8}{'수익금':>11}   {'재료 보유율(신용/주간대금/외국인/업종)':<32}")
print("  " + "-"*100)
tot = 0
for y in YRS:
    z = Z[Z.y == y]
    gsum = np.median([L[(L.y == y) & (L.rid == "P1")].gain.sum() for L in LOG])*CAPITAL
    ncnt = np.median([len(L[(L.y == y) & (L.rid == "P1")]) for L in LOG])
    tot += gsum
    mat = " ".join(f"{have[c].get(y, 0):>3.0f}%" for c in NEED)
    if not len(z):
        print(f"  {y:<6}{'—':>6}{'—':>7}{'—':>8}{'—':>8}{'—':>8}{'—':>11}   {mat}")
        continue
    print(f"  {y:<6}{len(z):>6}{(z._r>0).mean()*100:>6.0f}%{z._r.mean():>+7.1f}%{z._r.median():>+7.1f}%"
          f"{ncnt:>8.0f}{gsum/10000:>+10,.0f}만   {mat}")
print("  " + "-"*100)
print(f"  {'합계':<6}{len(Z):>6}{(Z._r>0).mean()*100:>6.0f}%{Z._r.mean():>+7.1f}%{Z._r.median():>+7.1f}%"
      f"{tot/10000:>+10,.0f}만")
sig = [y for y in YRS if not len(Z[Z.y == y])]
print(f"\n  신호 0건인 해: {', '.join(sig)}")
