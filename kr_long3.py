# -*- coding: utf-8 -*-
"""박시동 밴드 매매 변형 — **처음엔 안 사고 -10% 눌림에서만 산다** (2026-09-12).

kr_long2.py 에서 밴드 매매의 이득이 '익절' 이 아니라 '싸지면 다시 산다' 에서 나온다는 게
드러났다. 그러면 **첫 매수를 아예 빼고 눌림에서만 사면** 어떻게 되나. 눌림 매수만 순수하게
떼어내는 셈이다.

  기준가 b0 = 그날 시가(사지는 않는다. 값만 기억한다)
  · 종가가 b0×(1-진입%) 이하로 내려오면 **다음날 시가에 매수**
  · 종가가 b0×(1+익절%) 이상이면 **다음날 시가에 매도**
  · 다시 내려오면 또 산다. 구간이 끝나면 들고 있는 것만 종가 청산.

⚠ 이 방식은 **보유 비율이 확 낮아진다**. 같은 수익률이라도 계좌에 미치는 힘이 다르므로
  '노출당 수익'(평균 ÷ 보유비율)을 같이 적는다. 다만 남는 현금을 놀리는 것이 아니라면
  진짜 판정은 계좌에서 해야 한다 — 여기서는 한 종목 경로 비교다.

    python kr_long3.py [us]
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
US = len(sys.argv) > 1 and sys.argv[1] == "us"
W = 132


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)


log(("us_scan" if US else "kr_scan") + ".pkl 읽는 중")
K = pd.read_pickle(BASE / ("data/us_scan.pkl" if US else "data/kr_scan.pkl"))
if US: K = K[((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)]
else:  K = K[((K.close >= 1000) & (~K.pref.fillna(False))).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
ud = sorted(K.date.unique()); DI = {d: i for i, d in enumerate(ud)}
K["di"] = K.date.map(DI).astype(np.int32)
AR = K.groupby("date").amt20.rank(pct=True)
K["big"] = (AR >= 0.90).fillna(False)
CL = K.close.to_numpy(np.float64)
BUY = K.buy.to_numpy(np.float64); CST = K.cost.to_numpy(np.float64)
TK = K.ticker.to_numpy(); bnd = np.flatnonzero(np.r_[True, TK[1:] != TK[:-1], True])
ENDOF = np.empty(len(K), np.int64)
for s, e in zip(bnd[:-1], bnd[1:]): ENDOF[s:e] = e
LAST = len(ud) - 1


def nxo(k, j):
    """k일 종가로 판정 → 다음날 시가(= 그 행의 buy). 없으면 그날 종가."""
    v = BUY[k]
    return v if (v == v and v > 0 and k <= ENDOF[j] - 1) else CL[k]


def path(j, hold, entry, take, wait):
    """entry: 기준가 대비 몇 % 내려오면 사나(None 이면 즉시 매수)
       take : 기준가 대비 몇 % 오르면 파나(None 이면 안 판다)
       wait : True 면 **처음에 안 사고** 기다린다."""
    lim = min(ENDOF[j] - 1, j + hold); b0 = BUY[j]
    if not (b0 > 0): return np.nan, 0.0, 0
    lo = b0 * (1 - entry / 100) if entry is not None else None
    hi = b0 * (1 + take / 100) if take is not None else None
    eq = 1.0; on = 0; nt = 0
    held = not wait
    px = b0
    if held: eq *= (1 - CST[j] / 100); nt = 1
    for k in range(j + 1, lim + 1):
        c = CL[k]
        if held: on += 1
        if held and hi is not None and c >= hi:
            eq *= nxo(k, j) / px; eq *= (1 - CST[j] / 100); held = False
        elif (not held) and lo is not None and c <= lo:
            px = nxo(k, j); eq *= (1 - CST[j] / 100); held = True; nt += 1
    if held: eq *= CL[lim] / px
    return (eq - 1) * 100, on / max(lim - j, 1), nt


CFG = [
    ("그냥 보유(기준)",                 None, None, False),
    ("즉시매수 · +10% 익절 · -10% 재매수", 10,   10,   False),
    ("대기 · -5% 에 매수 · +10% 익절",    5,    10,   True),
    ("대기 · -10% 에 매수 · +10% 익절",   10,   10,   True),
    ("대기 · -15% 에 매수 · +10% 익절",   15,   10,   True),
    ("대기 · -20% 에 매수 · +10% 익절",   20,   10,   True),
    ("대기 · -10% 에 매수 · 0%(본전) 익절", 10,   0,    True),
    ("대기 · -10% 에 매수 · +20% 익절",   10,   20,   True),
    ("대기 · -10% 에 매수 · 안 팜",       10,   None, True),
]

qs = pd.Series(ud).groupby(pd.Series(ud).str[:4] + pd.Series(ud).str[4:6].astype(int).sub(1).floordiv(3).astype(str)).min()
STARTS = [d for d in qs.values if d >= "20050101"]

for HOLD in (250, 500):
    sec(f"{'미장' if US else '국내'} · 구간 {HOLD}거래일 · 거래대금 상위10% · 분기마다 시작")
    rows = {}
    for d in STARTS:
        i0 = DI.get(d)
        if i0 is None or i0 + HOLD + 1 > LAST: continue
        idx = np.flatnonzero((K.di.values == i0) & K.big.values)
        for nm, en, tk, wt in CFG:
            for j in idx:
                r, ex, nt = path(j, HOLD, en, tk, wt)
                if r == r: rows.setdefault(nm, []).append((r, ex, nt))
    print(f"  {'전략':<32}{'n':>8}{'평균':>8}{'중앙':>8}{'승률':>6}{'하위10%':>8}"
          f"{'보유비율':>8}{'매수횟수':>8}{'노출당 평균':>11}")
    for nm, *_ in CFG:
        v = rows.get(nm)
        if not v: continue
        r = np.array([x[0] for x in v]); e = np.array([x[1] for x in v]); n = np.array([x[2] for x in v])
        ex = e.mean()
        print(f"  {nm:<32}{len(r):>8,}{r.mean():>8.2f}{np.median(r):>8.2f}{(r > 0).mean() * 100:>5.0f}%"
              f"{np.percentile(r, 10):>8.1f}{ex * 100:>7.0f}%{n.mean():>8.2f}"
              f"{(r.mean() / ex if ex > 0.02 else float('nan')):>11.2f}")
log("끝")
