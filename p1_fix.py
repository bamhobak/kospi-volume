# -*- coding: utf-8 -*-
"""[조용한 신고가] 조율안 — 갈림길은 '그 종목 자신의 1년 성적' 이었다.

해부 결과(p1_dig.py):
  · 조건을 하나씩 빼 봐도 지는 5년(2009~13)은 -3~-5% 그대로다. 특정 조건의 잘못이 아니다.
    (업종 20일 조건만은 빼면 110→639건에 전체가 음수로 무너진다 — 이건 제 몫을 하고 있다)
  · 손절은 -7%~-20% 어디든 성적이 같다. 거의 안 걸린다.
  · 보유를 늘리면 이기는 해는 더 벌지만(60일 +11.6%) 지는 해는 더 잃는다(-4.8%).
  · 진입 시점 특성을 비교하니 딱 하나가 크게 갈렸다 — **ret250(자기 1년 수익률)**
    지는 5년 중앙값 +15.0% vs 이기는 4년 +28.7%. 신용잔고비(r16)도 84 vs 98 로 갈렸다.
가설: '조용히 신고가 근처' 가 통하려면 그 종목이 이미 1년을 끌어올린 상태여야 한다.
     박스권에서 겨우 제자리인 종목이 신고가 근처인 건 힘이 아니라 그냥 안 움직인 것이다.
사용: IX_FROM=2004-06-01 DART_FROM=20040101 PANEL_KP=panel_kp.pkl PANEL_KQ=panel_kq.pkl python p1_fix.py
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
KP, RULES = ns["KP"], ns["RULES"]
g = KP.groupby("ticker", sort=False)
C, HOLD, STOP = RULES["P1"][5], 40, 0.15

def take(cond, hold=HOLD, stop=STOP):
    low = pd.concat([g.low.shift(-i) for i in range(hold)], axis=1).min(axis=1)
    r = np.where((low <= KP.buy*(1-stop)).fillna(False), -stop*100 - KP.cost, KP[f"n{hold}"]) \
        if stop else KP[f"n{hold}"].values
    m = cond.fillna(False); X = KP[m].copy(); X["_r"] = r[m.values]; X = X.dropna(subset=["_r"])
    di = {x: i for i, x in enumerate(sorted(KP.date.unique()))}
    X["di"] = X.date.map(di); X = X.sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i+hold; keep.append(ix)
    return X.loc[keep].assign(y=lambda d: d.date.str[:4])

def ci(Z, n=1500, seed=0):
    rng = np.random.default_rng(seed); mo = Z.date.str[:6].values
    grp = [Z._r.values[mo == m] for m in np.unique(mo)]; k = len(grp)
    o = [np.concatenate([grp[i] for i in rng.integers(0, k, k)]).mean() for _ in range(n)]
    return np.percentile(o, 5)

YRS = [str(y) for y in range(2006, 2027)]
def line(nm, cond, hold=HOLD, stop=STOP):
    Z = take(cond, hold, stop)
    if len(Z) < 10: print(f"  {nm:<24} 표본 부족({len(Z)}건)"); return
    m = Z.groupby("y")._r.mean()
    cells = "".join(f"{m[y]:>+5.0f}" if y in m.index else f"{'·':>5}" for y in YRS)
    lo = ci(Z)
    print(f"  {nm:<24}{cells}{len(Z):>5}건{Z._r.mean():>+7.1f}%{(Z._r>0).mean()*100:>5.0f}%"
          f"{Z._r.median():>+6.1f}{lo:>+7.1f}{int((m>0).sum())}승{int((m<0).sum())}패")

print("[조용한 신고가] 자기 1년 수익률(ret250) 문턱 얹기 — 연도별 평균(%)")
print(f"  {'안':<24}" + "".join(f"{y[2:]:>5}" for y in YRS) + f"{'건수':>5}{'평균':>7}{'승률':>5}{'중앙':>6}{'CI하한':>7}{'연도':>7}")
print("  " + "-"*(24+5*len(YRS)+42))
line("현행", C)
for th in (0, 10, 20, 30, 40, 50):
    line(f"+ ret250 ≥{th}%", C & (KP.ret250 >= th))
print()
line("+ 신용잔고비 r16≥90", C & (KP.r16 >= 90))
line("+ 거래대금 ≥400억", C & (KP.amt20 >= 400))
line("+ ret250≥20 · r16≥90", C & (KP.ret250 >= 20) & (KP.r16 >= 90))
line("+ ret250≥20 · 60일보유", C & (KP.ret250 >= 20), 60)
