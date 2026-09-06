# -*- coding: utf-8 -*-
"""감사 3단계 — 과거 패널(panel_kp/kq)과 운영 패널(kp_ow/kq_ow)이 겹치는 2018~26 에서 같은 답을 내는가.
두 패널은 다른 경로로 만들어졌다. 같은 규칙을 넣어 건수·평균·승률이 비슷해야 둘 다 믿을 수 있다."""
import io, sys, os, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path
BASE = Path(__file__).parent
NAME = {"P7":"외인 매집","P1":"조용한 신고가","P4":"업종붕괴 이탈","P6":"깊은 이격","P3":"폭락반등",
        "P2":"조정매집","D1":"낙폭과대","D2":"저PBR 낙폭","P5":"자사주 낙폭"}
def run(kp, kq):
    os.environ.update(IX_FROM="2004-06-01", DART_FROM="20040101", PANEL_KP=kp, PANEL_KQ=kq)
    src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
    real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
    sys.stdout = real
    out = {}
    for rid,(K,hold,stop,pct,mx,cond) in ns["RULES"].items():
        col = f"n{hold}"; gg = K.groupby("ticker", sort=False)
        if stop:
            low = pd.concat([gg.low.shift(-i) for i in range(hold)], axis=1).min(axis=1)
            r = np.where((low <= K.buy*(1-stop)).fillna(False), -stop*100-K.cost, K[col])
        else: r = K[col].values
        m = cond.fillna(False) & (K.date>="20180101")
        X = K[m].copy(); X["_r"] = r[m.values]; X = X.dropna(subset=["_r"])
        di = {x:i for i,x in enumerate(sorted(K.date.unique()))}
        X["di"] = X.date.map(di); X = X.sort_values("di"); keep, last = [], {}
        for t,i,ix in zip(X.ticker.values, X.di.values, X.index):
            if last.get(t,-10**9) >= i: continue
            last[t] = i+hold; keep.append(ix)
        Z = X.loc[keep]; out[rid] = (len(Z), Z._r.mean(), (Z._r>0).mean()*100, set(zip(Z.ticker, Z.date)))
    return out
A = run("panel_kp.pkl", "panel_kq.pkl"); B = run("kp_ow.pkl", "kq_ow.pkl")
print("2018~2026 같은 규칙 · 두 패널 비교  (과거패널 vs 운영패널)")
print(f"  {'규칙':<12}{'건수':>14}{'평균':>18}{'승률':>14}{'신호 일치율':>12}")
print("  " + "-"*72)
for rid in A:
    na, ma, wa, sa = A[rid]; nb, mb, wb, sb = B[rid]
    ov = len(sa & sb)/max(min(len(sa),len(sb)),1)*100
    flag = "" if abs(ma-mb) < 2 and abs(na-nb)/max(na,nb,1) < 0.25 else "  ⚠"
    print(f"  {NAME[rid]:<12}{na:>6} vs {nb:<6}{ma:>+7.1f}% vs {mb:<+7.1f}%{wa:>5.0f}% vs {wb:<5.0f}%{ov:>10.0f}%{flag}")
