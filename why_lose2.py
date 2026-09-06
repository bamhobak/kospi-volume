# -*- coding: utf-8 -*-
"""지는 해 조율 2단계 — 후보안의 연도별 성적과, [폭락반등] 말고 지는 다른 규칙들.

1단계(why_lose.py)에서 [폭락반등] 은 '20일 낙폭 문턱을 깊게' 하는 쪽이 전 구간 개선으로 나왔다
(-20% → -30%: 2008~09 -4.0%→+3.1%, 2010~12 +1.3%→+7.3%, 전체 +17.5→+26.4%). 다만 신호가
302→173건으로 43% 줄고, 사용자가 세운 기준이 있다 — **가장 최근 해(2026)에 지면 채택 못 한다.**
그래서 연도별로 펼쳐 본다. 겸사겸사 [조용한 신고가](2009~2013 음수)·[낙폭과대](2010~12 음수)도
같은 방식으로 어디가 새는지 본다.
사용: IX_FROM=2004-06-01 DART_FROM=20040101 PANEL_KP=panel_kp.pkl PANEL_KQ=panel_kq.pkl python why_lose2.py
"""
import io, os, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES = ns["KP"], ns["KQ"], ns["RULES"]
for P in (KP, KQ):
    g = P.groupby("ticker", sort=False)
    for h in (10, 15, 30):
        if f"n{h}" not in P.columns: P[f"n{h}"] = (g.close.shift(-h)/P.buy-1)*100 - P.cost

def trades(P, cond, hold, stop):
    gg = P.groupby("ticker", sort=False)
    if stop:
        low = pd.concat([gg.low.shift(-i) for i in range(hold)], axis=1).min(axis=1)
        r = np.where((low <= P.buy*(1-stop)).fillna(False), -stop*100 - P.cost, P[f"n{hold}"])
    else:
        r = P[f"n{hold}"].values
    m = cond.fillna(False)
    X = P[m].copy(); X["_r"] = r[m.values]; X = X.dropna(subset=["_r"])
    d = sorted(P.date.unique()); di = {x: i for i, x in enumerate(d)}
    X["di"] = X.date.map(di); X = X.sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i+hold; keep.append(ix)
    return X.loc[keep]

YRS = [str(y) for y in range(2005, 2027)]
def byyear(nm, P, cond, hold, stop):
    Z = trades(P, cond, hold, stop)
    if not len(Z): print(f"  {nm:<22} 신호 없음"); return
    Z = Z.assign(y=Z.date.str[:4]); m = Z.groupby("y")._r.mean(); c = Z.groupby("y")._r.size()
    cells = "".join(f"{m[y]:>+7.0f}" if y in m.index else f"{'·':>7}" for y in YRS)
    n = "".join(f"{c[y]:>7}" if y in c.index else f"{'·':>7}" for y in YRS)
    w = int((m > 0).sum()); l = int((m < 0).sum())
    print(f"  {nm:<22}{cells}  {len(Z):>4}건 {Z._r.mean():+6.1f}% {w}승{l}패")
    print(f"  {'  (건수)':<22}{n}")

hdr = "".join(f"{y[2:]:>7}" for y in YRS)
print("[폭락반등] 후보안 — 연도별 평균 수익률(%)")
print(f"  {'안':<22}{hdr}")
print("  " + "-"*(22+7*len(YRS)+22))
_, H3, S3, _, _, C3 = RULES["P3"]
byyear("현행(-20%)", KP, C3, H3, S3)
byyear("D -25%", KP, C3 & (KP.ret20 <= -25), H3, S3)
byyear("D -30%", KP, C3 & (KP.ret20 <= -30), H3, S3)
byyear("D -25% + 15일보유", KP, C3 & (KP.ret20 <= -25), 15, S3)

print("\n[낙폭과대 D1] 후보안 — 연도별")
_, H1, S1, _, _, C1 = RULES["D1"]
byyear("현행(-20%)", KQ, C1, H1, S1)
byyear("D -25%", KQ, C1 & (KQ.ret20 <= -25), H1, S1)
byyear("D -30%", KQ, C1 & (KQ.ret20 <= -30), H1, S1)
byyear("D -35%", KQ, C1 & (KQ.ret20 <= -35), H1, S1)

print("\n[조용한 신고가 P1] — 연도별 (어디서 새나)")
_, HB, SB, _, _, CB = RULES["P1"]
byyear("현행", KP, CB, HB, SB)
byyear("+ 지수 60일선 위", KP, CB & (KP.get("ix60", pd.Series(True, index=KP.index)) if "ix60" in KP else CB), HB, SB) if False else None
byyear("보유 20일", KP, CB, 20, SB)
byyear("보유 30일", KP, CB, 30, SB)
