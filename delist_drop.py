# -*- coding: utf-8 -*-
"""계좌 시뮬이 **상장폐지 거래를 조용히 빼먹는가** (2026-09-12).

stats_2016.py 는 `n{h}` 를 쓴다. build_panel 은 보유 중 폐지되면 **마지막 종가**로
청산 처리한다 — 손실을 그대로 먹는다. 그래서 [저PBR 낙폭] 최악이 -97.4% 로 나온다.

portfolio.py 는 `exit = close.shift(-hold)` 를 쓰고 `dropna(subset=["exit"])` 한다.
폐지되면 shift 가 NaN 이라 **그 거래가 통째로 사라진다** — 손실을 안 먹는다.

둘 중 하나는 틀렸다. 크기를 잰다.

    python delist_drop.py
"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path
BASE = Path(__file__).parent

src = (BASE/"portfolio.py").read_text(encoding="utf-8")
ns = {"__file__": str(BASE/"portfolio.py")}
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
RULES, TRAIL = ns["RULES"], ns["TRAIL"]
NAME = {"P7":"외인 매집","P1":"조용한 신고가","P4":"업종붕괴 이탈","P6":"깊은 이격","P3":"폭락반등",
        "P2":"조정매집","D1":"낙폭과대","D2":"저PBR 낙폭","P5":"자사주 낙폭"}

print("\n" + "=" * 104)
print("규칙별 — 보유 중 폐지돼서 portfolio.py 가 버린 거래")
print("=" * 104)
print(f"  {'규칙':<14}{'신호':>7}{'버려짐':>8}{'비율':>7}{'버려진 것 평균':>14}{'남은 것 평균':>13}{'전부 평균':>11}{'차이':>9}")
tot = []
for rid in ["P7","P1","P2","P3","P4","P6","P5","D1","D2"]:
    K, hold, stop, pct, mx, cond = RULES[rid]
    g = K.groupby("ticker", sort=False)
    m = cond.fillna(False)
    nh = K[f"n{hold}"]
    ex = g.close.shift(-hold)
    X = K[m].copy()
    X["_n"] = nh[m]; X["_e"] = ex[m]
    X = X[X.date >= "20160101"].dropna(subset=["_n"])
    # 중복 제거 — stats_2016.py 와 같은 방식
    di = {x: i for i, x in enumerate(sorted(K.date.unique()))}
    X["di"] = X.date.map(di); X = X.sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i + hold; keep.append(ix)
    X = X.loc[keep]
    drop = X[X._e.isna()]; stay = X[X._e.notna()]
    if not len(X): continue
    d = drop._n.mean() if len(drop) else np.nan
    print(f"  {NAME[rid]:<14}{len(X):>7,}{len(drop):>8,}{len(drop)/len(X)*100:>6.1f}%"
          f"{d:>13.2f}%{stay._n.mean():>12.2f}%{X._n.mean():>10.2f}%"
          f"{X._n.mean()-stay._n.mean():>+8.2f}")
    tot.append((rid, len(X), len(drop), d, stay._n.mean(), X._n.mean()))

print("\n  '버려진 것' = 보유기간 안에 상장폐지된 거래. n{h} 는 마지막 종가로 청산해 손실을 먹고,")
print("  portfolio.py 는 NaN 이라 아예 안 산 것으로 친다. 비율이 0 이면 문제가 없다.")

print("\n" + "=" * 104)
print("버려진 거래는 실제로 어떤 것들인가 (있다면)")
print("=" * 104)
for rid in ["P7","P1","P2","P3","P4","P6","P5","D1","D2"]:
    K, hold, stop, pct, mx, cond = RULES[rid]
    g = K.groupby("ticker", sort=False)
    m = cond.fillna(False)
    X = K[m].copy(); X["_n"] = K[f"n{hold}"][m]; X["_e"] = g.close.shift(-hold)[m]
    X = X[(X.date >= "20160101") & X._n.notna() & X._e.isna()]
    if not len(X): continue
    print(f"\n  {NAME[rid]} — {len(X):,}건")
    print(X.nsmallest(5, "_n")[["date","ticker","name","buy","_n"]].to_string(index=False))
