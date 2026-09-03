# -*- coding: utf-8 -*-
"""과거 구간을 정본 규칙(portfolio.py 의 RULES)으로 그대로 잰다.

규칙을 손으로 옮겨 적으면 조건을 잘못 쓰는 사고가 난다(dev25 를 dma20 으로 쓰고
base() 를 빠뜨린 적이 있다). PANEL_KP/PANEL_KQ 로 패널만 갈아 끼우고 RULES 는
건드리지 않는다.

과거 패널에 없는 데이터가 규칙에 미치는 영향은 그대로 드러난다:
  · crc(신용잔고) 없음 → [폭락반등] 은 조건이 결측이라 신호 0 이 된다(정직한 결과)
  · PBR 없음 → [저PBR 낙폭] 도 마찬가지
  · 부채비율 없음 → [낙폭과대] 는 '결측이면 통과' 라 영향 없음
  · above20/ret250 없음 → [조용한 신고가] 의 '지속상승 배제' 만 느슨해진다
사용: PANEL_KP=panel_kp.pkl PANEL_KQ=panel_kq.pkl python measure_hist.py
"""
import io, sys, os, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
src = (BASE/"portfolio.py").read_text(encoding="utf-8")
ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
RULES = ns["RULES"]
DISP = {"P7":"P1","P1":"P2","P4":"P3","P6":"P4","P3":"P5","P2":"P6","D1":"D1","D2":"D2","P5":"A1"}
NAME = {"P7":"외인 매집","P1":"조용한 신고가","P4":"업종붕괴 이탈","P6":"깊은 이격","P3":"폭락반등",
        "P2":"조정매집","D1":"낙폭과대","D2":"저PBR 낙폭","P5":"자사주 낙폭"}
ORDER = ["P7","P1","P4","P6","P3","P2","D1","D2","P5"]
PER = [("2016~2017","20160101","20171231"), ("2018~2022","20180101","20221231"),
       ("2023~2026","20230101","20991231")]
def trades(K, hold, stop, cond, lo, hi):
    col = f"n{hold}"
    if col not in K.columns: return None
    g = K.groupby("ticker", sort=False)
    if stop:
        low = pd.concat([g.low.shift(-i) for i in range(hold)], axis=1).min(axis=1)
        r = np.where((low <= K.buy*(1-stop)).fillna(False), -stop*100 - K.cost, K[col])
    else: r = K[col].values
    m = cond.fillna(False) & (K.date>=lo) & (K.date<=hi)
    X = K[m].copy(); X["_r"] = r[m.values]; X = X.dropna(subset=["_r"])
    d = sorted(K.date.unique()); di = {x:i for i,x in enumerate(d)}
    X["di"] = X.date.map(di); X = X.sort_values("di")
    keep, last = [], {}
    for t,i,ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t,-10**9) >= i: continue
        last[t] = i+hold; keep.append(ix)
    return X.loc[keep]
print(f"  패널: {os.environ.get('PANEL_KP','kp_ow.pkl')} / {os.environ.get('PANEL_KQ','kq_ow.pkl')}\n")
print(f"  {'':<3}{'규칙':<14}" + "".join(f"{p[0]:>26}" for p in PER))
print("  " + "-"*93)
for rid in ORDER:
    K, hold, stop, pct, mx, cond = RULES[rid]
    cells = ""
    for _, lo, hi in PER:
        Z = trades(K, hold, stop, cond, lo, hi)
        if Z is None: cells += f"{'컬럼 없음':>24}"; continue
        if len(Z) == 0: cells += f"{'신호 없음':>24}"; continue
        v = Z._r.to_numpy()
        cells += f"{len(Z):>7}건{v.mean():>+8.2f}% 승{(v>0).mean()*100:>3.0f}%"
    print(f"  {DISP[rid]:<3}{NAME[rid]:<14}{cells}")
