# -*- coding: utf-8 -*-
"""박시동 '장기투자는 묻어두기가 아니다' — 밴드 매매 vs 매수후보유 (2026-09-12).

원문: "여러분이 7만 원에 샀다고 해 볼게요. ... 7만 원에 사서 8만 원이 됐다. 냅다 파시는
거라니까요. ... 66,000원이 됐죠? 지금 사는 거예요. 그 7만 원 되면 오케이. 또 팔아."
→ **기준가를 잡고 위로 X% 오르면 팔고, 아래로 Y% 내리면 다시 산다.** 같은 종목을 계속.

같은 종목·같은 시작일·같은 기간에서 그냥 들고 있는 것과 짝비교한다.
매매할 때마다 **세금·슬리피지(cost)를 낸다** — 이게 이 주장의 진짜 시험대다.

    python kr_long2.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
W = 124


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)


log("kr_scan.pkl 읽는 중")
K = pd.read_pickle(BASE / "data/kr_scan.pkl")
K = K[((K.close >= 1000) & (~K.pref.fillna(False))).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
ud = sorted(K.date.unique()); DI = {d: i for i, d in enumerate(ud)}
K["di"] = K.date.map(DI).astype(np.int32)
AR = K.groupby("date").amt20.rank(pct=True)
K["big"] = (AR >= 0.90).fillna(False)                # 영상이 말하는 '아는 종목' = 대형주
CL = K.close.to_numpy(np.float64); OP = K.open.to_numpy(np.float64)
BUY = K.buy.to_numpy(np.float64); CST = K.cost.to_numpy(np.float64)
TK = K.ticker.to_numpy()
bnd = np.flatnonzero(np.r_[True, TK[1:] != TK[:-1], True])
ENDOF = np.empty(len(K), np.int64)
for s, e in zip(bnd[:-1], bnd[1:]): ENDOF[s:e] = e
LASTPOS = len(ud) - 1

# 시작일 — 분기 첫 거래일(표본을 줄이되 고르게)
qs = pd.Series(ud).groupby(pd.Series(ud).str[:4] + pd.Series(ud).str[4:6].astype(int).sub(1).floordiv(3).astype(str)).min()
STARTS = [d for d in qs.values if d >= "20050101"]
log(f"시작일 {len(STARTS)}개 ({STARTS[0]}~{STARTS[-1]})")


def path(j, hold, up, dn):
    """j 행에서 시작. up% 오르면 팔고, 기준가 대비 -dn% 면 다시 산다. 없으면 그냥 보유.
       기준가는 **최초 매수가** 로 고정한다(영상이 '7만원' 을 기준으로 말한다)."""
    lim = min(ENDOF[j] - 1, j + hold)
    b0 = BUY[j]
    if not (b0 > 0): return np.nan, 0, 0.0
    if up is None:                                    # 매수후보유
        return (CL[lim] / b0 - 1) * 100 - CST[j], 1, 1.0
    eq = 1.0; nt = 1; held = True; px = b0; ondays = 0
    tp = b0 * (1 + up / 100); re = b0 * (1 - dn / 100) if dn is not None else -1
    eq *= (1 - CST[j] / 100)
    for k in range(j + 1, lim + 1):
        c = CL[k]
        if held: ondays += 1
        if held and c >= tp:
            s = OP[k + 1] if k + 1 <= ENDOF[j] - 1 else c
            eq *= s / px; eq *= (1 - CST[j] / 100); held = False
        elif (not held) and dn is not None and c <= re:
            px = OP[k + 1] if k + 1 <= ENDOF[j] - 1 else c
            eq *= (1 - CST[j] / 100); held = True; nt += 1
    if held: eq *= CL[lim] / px
    n = max(lim - j, 1)
    return (eq - 1) * 100, nt, ondays / n


CFG = [("그냥 보유(매수후보유)", None, None),
       ("+10% 팔고 -10% 재매수", 10, 10),
       ("+15% 팔고 -10% 재매수", 15, 10),
       ("+20% 팔고 -15% 재매수", 20, 15),
       ("+10% 팔고 -20% 재매수", 10, 20),
       ("+10%에 팔고 재매수 안 함", 10, None)]

for HOLD in (250, 500):
    sec(f"보유 구간 {HOLD}거래일 (약 {HOLD/252:.0f}년) · 거래대금 상위10% 종목 · 분기마다 시작")
    rows = {}
    for d in STARTS:
        i0 = DI[d]
        if i0 + HOLD + 1 > LASTPOS: continue          # 아직 안 끝난 구간은 세지 않는다
        idx = np.flatnonzero((K.di.values == i0) & K.big.values)
        for nm, up, dn in CFG:
            for j in idx:
                r, nt, ex = path(j, HOLD, up, dn)
                if r == r: rows.setdefault(nm, []).append((r, nt, ex))
    print(f"  {'전략':<24}{'n':>9}{'평균':>9}{'중앙':>9}{'승률':>7}{'하위10%':>9}{'상위10%':>9}{'매매횟수':>9}{'보유비율':>9}")
    base = None
    for nm, up, dn in CFG:
        v = rows.get(nm)
        if not v: continue
        r = np.array([x[0] for x in v]); nt = np.array([x[1] for x in v])
        exp = np.array([x[2] for x in v])
        if base is None: base = np.median(r)
        print(f"  {nm:<24}{len(r):>9,}{r.mean():>9.2f}{np.median(r):>9.2f}{(r > 0).mean() * 100:>6.0f}%"
              f"{np.percentile(r, 10):>9.1f}{np.percentile(r, 90):>9.1f}{nt.mean():>9.2f}{exp.mean()*100:>8.0f}%"
              + ("" if nm.startswith("그냥") else f"   중앙 {np.median(r) - base:+.2f}%p"))
log("끝")
