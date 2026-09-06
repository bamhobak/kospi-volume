# -*- coding: utf-8 -*-
"""[조용한 신고가] 는 왜 2007~2013 내내 졌나 — 국면 게이트가 없다.

이 규칙만 아홉 중 유일하게 국면 조건이 없다(P3·P4·P6·D1·D2 는 하락장, P7 은 상승장).
'조용히 신고가 근처' 는 시장이 오를 때만 이어진다는 가설. 지수 국면을 얹어 본다.
사용: IX_FROM=2004-06-01 DART_FROM=20040101 PANEL_KP=panel_kp.pkl PANEL_KQ=panel_kq.pkl python why_lose6.py
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
KP, RULES, up60, dn60 = ns["KP"], ns["RULES"], ns["up60"], ns["dn60"]
IX, UP20, UP60 = ns["IX"], ns["UP20"], ns["UP60"]
# 지수 200일선 위/아래 — 더 느린 국면자
_ix = IX[IX.Close > 0].copy(); _ix["d"] = _ix.index.strftime("%Y%m%d")
ma200 = dict(zip(_ix.d, _ix.Close > _ix.Close.rolling(200).mean()))
ma120 = dict(zip(_ix.d, _ix.Close > _ix.Close.rolling(120).mean()))
r250 = dict(zip(_ix.d, _ix.Close.pct_change(250)*100))
KP["ix200"] = KP.date.map(ma200); KP["ix120"] = KP.date.map(ma120); KP["ixr250"] = KP.date.map(r250)

def trades(P, cond, hold, stop):
    gg = P.groupby("ticker", sort=False)
    if stop:
        low = pd.concat([gg.low.shift(-i) for i in range(hold)], axis=1).min(axis=1)
        r = np.where((low <= P.buy*(1-stop)).fillna(False), -stop*100 - P.cost, P[f"n{hold}"])
    else: r = P[f"n{hold}"].values
    m = cond.fillna(False); X = P[m].copy(); X["_r"] = r[m.values]; X = X.dropna(subset=["_r"])
    d = sorted(P.date.unique()); di = {x: i for i, x in enumerate(d)}
    X["di"] = X.date.map(di); X = X.sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i+hold; keep.append(ix)
    return X.loc[keep]

YRS = [str(y) for y in range(2006, 2027)]
def row(nm, cond, hold=40, stop=0.15):
    Z = trades(KP, cond, hold, stop)
    if not len(Z): print(f"  {nm:<20} 신호 없음"); return
    Z = Z.assign(y=Z.date.str[:4]); m = Z.groupby("y")._r.mean(); c = Z.groupby("y")._r.size()
    cells = "".join(f"{m[y]:>+6.0f}" if y in m.index else f"{'·':>6}" for y in YRS)
    print(f"  {nm:<20}{cells} {len(Z):>4}건 {Z._r.mean():+6.1f}% {(Z._r>0).mean()*100:.0f}% "
          f"{int((m>0).sum())}승{int((m<0).sum())}패")
    print(f"  {'  (건수)':<20}" + "".join(f"{c[y]:>6}" if y in c.index else f"{'·':>6}" for y in YRS))
C = RULES["P1"][5]
print("[조용한 신고가] 국면 게이트 얹기 — 연도별 평균(%)")
print(f"  {'안':<20}" + "".join(f"{y[2:]:>6}" for y in YRS))
print("  " + "-"*(20+6*len(YRS)+30))
row("현행(게이트 없음)", C)
row("+ 지수 60일선 위", C & up60(KP))
row("+ 지수 120일선 위", C & (KP.ix120 == True))
row("+ 지수 200일선 위", C & (KP.ix200 == True))
row("+ 지수 1년 수익 ≥0", C & (KP.ixr250 >= 0))
row("+ 지수 1년 수익 ≥10", C & (KP.ixr250 >= 10))
row("- 하락장 제외만", C & ~dn60(KP))

# ── 같은 날 유니버스 평균 대비 초과 — '진 게 아니라 시장이 더 빠진 것' 인지 가른다
print("\n같은 날짜·같은 시장 유니버스 평균 대비 초과(40일 보유 기준)")
uni = KP.dropna(subset=["n40"]).groupby("date").n40.mean()
def excess(nm, cond, hold=40, stop=0.15):
    Z = trades(KP, cond, hold, stop)
    if not len(Z): return
    Z = Z.assign(y=Z.date.str[:4], b=Z.date.map(uni))
    Z["ex"] = Z._r - Z.b
    m = Z.groupby("y").ex.mean()
    cells = "".join(f"{m[y]:>+6.0f}" if y in m.index else f"{'·':>6}" for y in YRS)
    print(f"  {nm:<20}{cells} {Z.ex.mean():>+6.1f}% {int((m>0).sum())}승{int((m<0).sum())}패")
print(f"  {'안':<20}" + "".join(f"{y[2:]:>6}" for y in YRS))
excess("조용한신고가 현행", C)
excess("+ 지수 60일선 위", C & up60(KP))
# 참고: 다른 규칙들도 초과로 다시 본다
for rid, hold, stop, nm in [("P3",20,None,"폭락반등"), ("P4",5,0.15,"업종붕괴이탈"),
                            ("P6",5,0.10,"깊은이격"), ("P7",60,None,"외인매집")]:
    P = RULES[rid][0]
    if f"n{hold}" not in P.columns: continue
    u2 = P.dropna(subset=[f"n{hold}"]).groupby("date")[f"n{hold}"].mean()
    Z = trades(P, RULES[rid][5], hold, stop)
    if not len(Z): print(f"  {nm:<20} 신호 없음"); continue
    Z = Z.assign(y=Z.date.str[:4]); Z["ex"] = Z._r - Z.date.map(u2)
    m = Z.groupby("y").ex.mean()
    cells = "".join(f"{m[y]:>+6.0f}" if y in m.index else f"{'·':>6}" for y in YRS)
    print(f"  {nm:<20}{cells} {Z.ex.mean():>+6.1f}% {int((m>0).sum())}승{int((m<0).sum())}패")
