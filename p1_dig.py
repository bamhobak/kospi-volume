# -*- coding: utf-8 -*-
"""[조용한 신고가] 해부 — 2009~2013 은 왜 지고 2020·2023 은 왜 이겼나.

전제 확인 끝: 그 시절 신호가 없는 게 아니라(재료 보유율 97~100%) 조건이 진짜 안 걸린 해가 9년,
걸린 해 중 2009~2013 5년은 40건 승률 14~50%였다. 국면 게이트 다섯 가지로는 안 고쳐졌다.
그래서 규칙의 '부품' 을 하나씩 뜯어 본다.
  ① 어느 조건이 실제로 거르고 있나(각 항을 하나씩 빼 보면 성적이 어떻게 변하나)
  ② 40일 보유가 맞나 — 보유기간별 곡선
  ③ 손절 -15% 가 맞나
  ④ 이기는 해와 지는 해의 신호는 뭐가 다른가(진입 시점 특성 비교)
사용: IX_FROM=2004-06-01 DART_FROM=20040101 PANEL_KP=panel_kp.pkl PANEL_KQ=panel_kq.pkl python p1_dig.py
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
KP, RULES, base = ns["KP"], ns["RULES"], ns["base"]
g = KP.groupby("ticker", sort=False)
for h in (5,10,15,20,25,30,40,50,60):
    if f"n{h}" not in KP.columns: KP[f"n{h}"] = (g.close.shift(-h)/KP.buy-1)*100 - KP.cost

def take(cond, hold, stop):
    if stop:
        low = pd.concat([g.low.shift(-i) for i in range(hold)], axis=1).min(axis=1)
        r = np.where((low <= KP.buy*(1-stop)).fillna(False), -stop*100 - KP.cost, KP[f"n{hold}"])
    else: r = KP[f"n{hold}"].values
    m = cond.fillna(False); X = KP[m].copy(); X["_r"] = r[m.values]; X = X.dropna(subset=["_r"])
    di = {x: i for i, x in enumerate(sorted(KP.date.unique()))}
    X["di"] = X.date.map(di); X = X.sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i+hold; keep.append(ix)
    return X.loc[keep].assign(y=lambda d: d.date.str[:4])

BAD = ("2009", "2010", "2011", "2012", "2013")     # 지는 5년
GOOD = ("2020", "2021", "2023", "2024")            # 이기는 4년
def line(nm, Z):
    if not len(Z): print(f"  {nm:<26} 신호 없음"); return
    b = Z[Z.y.isin(BAD)]; o = Z[Z.y.isin(GOOD)]
    f = lambda z: f"{len(z):>4}건{z._r.mean():>+7.1f}%{(z._r>0).mean()*100:>5.0f}%" if len(z) else f"{'—':>17}"
    yy = Z.groupby("y")._r.mean()
    print(f"  {nm:<26}{f(Z)}{f(b)}{f(o)}{int((yy>0).sum())}승{int((yy<0).sum())}패")

# 규칙 항을 하나씩 뜯는다
TERMS = {
 "고점 -10% 이내(fromhi)": KP.fromhi >= -10,
 "신용잔고비 <120(r16)":   KP.r16 < 120,
 "주간거래대금 ≤120(rw1)": KP.rw1 <= 120,
 "외국인 5일 ≥3(fw5)":     KP.fw5 >= 3,
 "외국인 60일 ≥1(fw60)":   KP.fw60 >= 1,
 "변동성 ≤2(vol20)":       KP.vol20 <= 2,
 "업종 20일 ≤0.5(sr20)":   KP.sr20 <= 0.5,
 "20일 등락 ≤5(ret20)":    KP.ret20 <= 5,
 "과열 제외(above20/250)": ~((KP.above20>70)&(KP.ret250>120)),
}
FULL = base(KP,200)
for c in TERMS.values(): FULL = FULL & c
print("① 조건을 하나씩 빼 보면 (40일·손절15%)")
print(f"  {'':<26}{'전체':>17}{'지는 5년(09~13)':>17}{'이기는 4년':>17}  연도")
line("현행 전부", take(FULL, 40, 0.15))
for nm, c in TERMS.items():
    sub = base(KP,200)
    for k, v in TERMS.items():
        if k != nm: sub = sub & v
    line(f"  ↳ {nm} 뺌", take(sub, 40, 0.15))

print("\n② 보유기간 (손절 -15%)")
print(f"  {'':<26}{'전체':>17}{'지는 5년':>17}{'이기는 4년':>17}  연도")
for h in (5,10,15,20,25,30,40,50,60):
    line(f"{h}일 보유", take(FULL, h, 0.15))

print("\n③ 손절 (40일 보유)")
print(f"  {'':<26}{'전체':>17}{'지는 5년':>17}{'이기는 4년':>17}  연도")
for st in (None, 0.07, 0.10, 0.15, 0.20):
    line(f"손절 {'없음' if not st else f'-{st*100:.0f}%'}", take(FULL, 40, st))

print("\n④ 이기는 해와 지는 해의 신호는 뭐가 다른가 (진입 시점 중앙값)")
Z = take(FULL, 40, 0.15)
cols = [c for c in ["fromhi","r16","rw1","fw5","fw60","vol20","sr20","ret20","ret250","above20",
                    "amt20","dev25"] if c in Z.columns]
print(f"  {'항목':<12}{'지는 5년':>12}{'이기는 4년':>12}{'차이':>10}")
for c in cols:
    b = Z[Z.y.isin(BAD)][c].median(); o = Z[Z.y.isin(GOOD)][c].median()
    print(f"  {c:<12}{b:>12.1f}{o:>12.1f}{o-b:>+10.1f}")
