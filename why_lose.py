# -*- coding: utf-8 -*-
"""지는 해의 원인 찾기 — [폭락반등] 은 왜 2008·2011 에 졌나, 조율할 곳이 있나.

관찰(2026-09-06 · 21년 재검증): [폭락반등] 은 2020년 111건 +32.2% 가 전체를 끌어올리고
2008년 33건 −4.0%(승률 36%) · 2011년 7건 −2.9% 로 졌다. 코로나는 V자, 금융위기는 계단식
하락이었다. '폭락 후 신용잔고가 줄면 산다' 는 반등이 곧 온다는 전제에 기대는데 그게 깨진다.

가설과 조율안을 **21년 전 구간**에서 잰다(2010~2017 박스권 포함 — 거기서 죽는 안은 실전에서 논다).
  A) 손절을 넣는다(현재 없음) — 계단식 하락에서 손실을 끊는다
  B) 반등 확인 후 산다 — 신호일이 양봉일 때만
  C) 시장이 멈춘 뒤 산다 — 코스피가 5일선 위로 올라온 뒤
  D) 낙폭 문턱을 더 깊게 — 진짜 투매만
  E) 보유를 짧게 — 20일 → 10일
비교 기준은 현행 정의 그대로. 판정은 구간별 평균·승률과 '지는 해 수' 로 본다.
사용: IX_FROM=2004-06-01 DART_FROM=20040101 PANEL_KP=panel_kp.pkl PANEL_KQ=panel_kq.pkl python why_lose.py
"""
import io, os, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

BASE = Path(__file__).parent
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES, base, dn60 = ns["KP"], ns["KQ"], ns["RULES"], ns["base"], ns["dn60"]

# 코스피 지수 상태 — '시장이 멈췄나' 판정용
IX = fdr.DataReader("KS11", "2004-06-01"); IX = IX[IX.Close > 0].copy()
IX["date"] = IX.index.strftime("%Y%m%d")
IX["ma5"] = IX.Close.rolling(5).mean()
IX["ix_up5"] = IX.Close > IX.ma5
IX["ix_ret5"] = IX.Close.pct_change(5)*100
KP["ix_up5"] = KP.date.map(dict(zip(IX.date, IX.ix_up5)))
KP["ix_ret5"] = KP.date.map(dict(zip(IX.date, IX.ix_ret5)))
g = KP.groupby("ticker", sort=False)
KP["green"] = KP.close > KP.open                      # 신호일 양봉
for h in (10, 15):
    if f"n{h}" not in KP.columns: KP[f"n{h}"] = (g.close.shift(-h)/KP.buy-1)*100 - KP.cost

_, HOLD, STOP, _, _, COND = RULES["P3"]               # [폭락반등] 현행
PER = [("2005~07","20050101","20071231"), ("2008~09","20080101","20091231"),
       ("2010~12","20100101","20121231"), ("2013~17","20130101","20171231"),
       ("2018~22","20180101","20221231"), ("2023~26","20230101","20991231")]

def trades(cond, hold, stop):
    col = f"n{hold}"
    gg = KP.groupby("ticker", sort=False)
    if stop:
        low = pd.concat([gg.low.shift(-i) for i in range(hold)], axis=1).min(axis=1)
        r = np.where((low <= KP.buy*(1-stop)).fillna(False), -stop*100 - KP.cost, KP[col])
    else:
        r = KP[col].values
    X = KP[cond.fillna(False)].copy(); X["_r"] = r[cond.fillna(False).values]
    X = X.dropna(subset=["_r"])
    d = sorted(KP.date.unique()); di = {x: i for i, x in enumerate(d)}
    X["di"] = X.date.map(di); X = X.sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i+hold; keep.append(ix)
    return X.loc[keep]

def report(nm, cond, hold=HOLD, stop=STOP):
    Z = trades(cond, hold, stop)
    if not len(Z): print(f"  {nm:<30} 신호 없음"); return
    cells = ""
    for _, lo, hi in PER:
        z = Z[(Z.date >= lo) & (Z.date <= hi)]
        cells += f"{len(z):>4}건{z._r.mean():>+7.1f}%" if len(z) else f"{'—':>12}"
    y = Z.assign(y=Z.date.str[:4]).groupby("y")._r.mean()
    lose = int((y < 0).sum()); win = int((y > 0).sum())
    print(f"  {nm:<30}{cells}{len(Z):>6}건{Z._r.mean():>+7.1f}%{(Z._r>0).mean()*100:>5.0f}%"
          f"{Z._r.median():>+7.1f}{win:>4}승{lose:>3}패")

print("[폭락반등] 조율안 비교 — 21년 전 구간 (코스피)")
print(f"  {'안':<30}" + "".join(f"{p[0]:>12}" for p in PER) + f"{'전체':>6}{'평균':>7}{'승률':>5}{'중앙':>7}{'연도':>8}")
print("  " + "-"*136)
report("현행", COND)
report("A) 손절 -15%", COND, stop=0.15)
report("A) 손절 -20%", COND, stop=0.20)
report("A) 손절 -25%", COND, stop=0.25)
report("B) 신호일 양봉만", COND & (KP.green == True))
report("C) 코스피 5일선 위", COND & (KP.ix_up5 == True))
report("C) 코스피 5일 수익률 ≥0", COND & (KP.ix_ret5 >= 0))
report("D) 20일 낙폭 -25% 이하", COND & (KP.ret20 <= -25))
report("D) 20일 낙폭 -30% 이하", COND & (KP.ret20 <= -30))
report("E) 보유 10일", COND, hold=10)
report("E) 보유 15일", COND, hold=15)
report("B+C 양봉·지수5일선", COND & (KP.green == True) & (KP.ix_up5 == True))
report("A+B 손절20·양봉", COND & (KP.green == True), stop=0.20)
