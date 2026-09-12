# -*- coding: utf-8 -*-
"""**Booming Bulls 스윙 매매법** 실측 (2026-09-12).

유튜브 'Swing Trading Strategy || Stock Selection' (Anish Singh Thakur · Booming Bulls,
인도). 38분 중 규칙은 다섯 줄이다.

  ① 유니버스 — Nifty 50 / 100 / F&O 안에서 30~50종목만 본다(대형·유동).
  ② 일봉에서 '흥미로운 자리' = **돌파(breakout)** 또는 **되돌림 재확인(retest)**.
     되돌림은 피보나치 **황금구간 38.2~61.8%** 지지를 같이 본다.
  ③ 진입은 1h·4h 로 내려가 **양봉을 확인한 뒤**. ("We will enter in green only")
  ④ 손절 = **직전 캔들 저가 아래**.
  ⑤ 목표 = **RRR 1:1.4~1.5** ("손절이 70이면 목표는 최소 100, 140, 150").
  ⑥ 목표의 50%(또는 1차 목표) 도달하면 손절을 **본전으로** 올린다. 그 전엔 건드리지 않는다.
     "Don't trail fast... start trailing only when its 50% or when target no.1 hits"

일봉으로 옮길 때 **없는 것을 지어내지 않는다**:
  · 1h·4h 가 없으므로 '양봉 확인' 은 **신호일 종가>시가** 로 본다. 진입은 늘 다음날 시가.
  · '흥미로운 자리' 는 재량이라 기계화 가능한 셋 만 쓴다 — 돌파 · 돌파 후 재확인 · 황금구간.
  · 손절·목표는 **종가로 판정하고 다음날 시가에 청산**한다(집안 규율 · 오늘 배운 보수 체결).

    python bb_swing.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
from vp_lib import boot_ci

BASE = Path(__file__).parent
TR1, VA0 = "20221231", "20230101"
W = 150


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)


log("kr_scan.pkl 읽는 중")
K = pd.read_pickle(BASE / "data/kr_scan.pkl")
K = K[((K.close >= 1000) & (~K.pref.fillna(False))).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
ud = sorted(K.date.unique())
K["di"] = K.date.map({d: i for i, d in enumerate(ud)}).astype(np.int32)
G = K.groupby("ticker", sort=False)
JW = (K.jw if "jw" in K.columns else pd.Series(False, index=K.index)).fillna(False)
log(f"준비 {len(K):,}행 · {K.ticker.nunique():,}종목 · {K.date.min()}~{K.date.max()}")

# ── 유니버스 3종 — 영상은 Nifty50/100/F&O 라는 **대형·유동**만 본다
AR = K.groupby("date").amt20.rank(pct=True)
CR = K.groupby("date").marcap.rank(pct=True) if "marcap" in K.columns else AR
UNIS = [("거래대금 상위40%(집안 기준)", (AR >= 0.60).fillna(False)),
        ("거래대금 상위10%(Nifty100 급)", (AR >= 0.90).fillna(False)),
        ("거래대금 상위3%(Nifty50 급)", (AR >= 0.97).fillna(False))]

# ── 셋업 재료 ─────────────────────────────────────────────────────────
log("셋업 계산 중")
K["hi60p"] = G.high.transform(lambda s: s.rolling(60).max()).groupby(K.ticker).shift(1)
K["green"] = (K.close > K.open).fillna(False)
BRK = (K.close > K.hi60p).fillna(False)                     # 60일 고점 돌파(종가)
# 되돌림 재확인 — 최근 20일 안에 돌파가 있었고, 그때의 기준선까지 내려왔다가 양봉
lvl = K.hi60p.where(BRK)
K["lvl"] = lvl.groupby(K.ticker).ffill()                     # 마지막으로 깬 레벨
K["since"] = (BRK.groupby(K.ticker).cumsum())
_last_brk_di = K.di.where(BRK).groupby(K.ticker).ffill()
K["agebrk"] = K.di - _last_brk_di
RT = ((K.agebrk.between(1, 20)) & (K.low <= K.lvl * 1.03) & (K.close >= K.lvl * 0.99)
      & K.green).fillna(False)

# 황금구간 — 직전 확정 스윙 저점→고점의 38.2~61.8% 되돌림에 저가가 닿고 양봉
L = 7; w = 2 * L + 1
ph = G.high.transform(lambda s: s.shift(L).where(s.shift(L) == s.rolling(w).max()))
pl = G.low.transform(lambda s: s.shift(L).where(s.shift(L) == s.rolling(w).min()))
K["sh"] = ph.groupby(K.ticker).ffill(); K["sl"] = pl.groupby(K.ticker).ffill()
leg = K.sh - K.sl
f382 = K.sh - leg * 0.382; f618 = K.sh - leg * 0.618
GOLD = ((leg > 0) & (K.sh > K.sl * 1.10) & (K.low <= f382) & (K.low >= f618 * 0.98)
        & (K.close > f618) & K.green).fillna(False)

SETUPS = [("① 돌파 (60일 고점)", BRK & K.green),
          ("② 돌파 후 재확인(retest)", RT),
          ("③ 황금구간 38.2~61.8 되돌림", GOLD),
          ("②+③ (되돌림 계열 합)", (RT | GOLD))]

CLOSE = K.close.to_numpy(np.float64); OPEN = K.open.to_numpy(np.float64)
LOW = K.low.to_numpy(np.float64); BUY = K.buy.to_numpy(np.float64)
COST = K.cost.to_numpy(np.float64); TK = K.ticker.to_numpy()
bnd = np.flatnonzero(np.r_[True, TK[1:] != TK[:-1], True])
ENDOF = np.empty(len(K), np.int64)
for s, e in zip(bnd[:-1], bnd[1:]): ENDOF[s:e] = e


def run_exit(idx, rrr, maxhold, be_trail):
    """영상식 청산. 종가로 판정하고 **다음날 시가**에 판다.
       be_trail=True 면 목표의 50% 를 종가로 넘긴 뒤부터 손절을 진입가로 올린다."""
    ret = np.full(len(idx), np.nan); hold = np.zeros(len(idx), np.int32)
    why = np.zeros(len(idx), np.int8)          # 0 만기 · 1 손절 · 2 목표 · 3 본전
    for z, j in enumerate(idx):
        b = BUY[j]; sl = LOW[j]
        if not (b > 0) or not (sl > 0) or sl >= b: continue
        risk = b - sl
        tp = b + risk * rrr
        half = b + risk * rrr * 0.5
        lim = min(ENDOF[j] - 1, j + maxhold)
        ex = np.nan; armed = False
        for k in range(j + 1, lim + 1):
            c = CLOSE[k]
            if be_trail and not armed and c >= half: armed = True
            floor = b if armed else sl
            if c <= floor or c >= tp:
                ex = OPEN[k + 1] if k + 1 <= ENDOF[j] - 1 else c
                hold[z] = k - j
                why[z] = 2 if c >= tp else (3 if armed else 1); break
        if not (ex == ex):
            ex = CLOSE[lim]; hold[z] = lim - j
        ret[z] = (ex / b - 1) * 100 - COST[j]
    return ret, hold, why


BEN = {}
def bench(uni, h):
    k = (id(uni), h)
    if k not in BEN:
        BEN[k] = K[uni].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean()
    return BEN[k]


def judge(tag, cond, uni, rrr, maxhold, be_trail, minn=40):
    m = (cond & uni & ~JW).fillna(False).to_numpy()
    idx = np.flatnonzero(m)
    if len(idx) < minn: print(f"  {tag:<44}{len(idx):>6} (부족)"); return None
    ret, hold, why = run_exit(idx, rrr, maxhold, be_trail)
    X = K.iloc[idx].copy(); X["r"] = ret; X["hd"] = hold; X["why"] = why
    X = X[X.r.notna() & (X.date >= "20160101")].sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i: continue
        last[t] = i + maxhold; keep.append(ix)
    Y = X.loc[keep].copy()
    if len(Y) < minn: print(f"  {tag:<44}{len(Y):>6} (부족)"); return None
    hh = maxhold if maxhold in (5, 10, 20, 40, 60) else 20
    Y["ex"] = Y.r - Y.date.map(bench(uni, hh))
    Y["yr"] = Y.date.str[:4]; Y["ym"] = Y.date.str[:6]
    tr = Y[Y.date <= TR1]; va = Y[Y.date >= VA0]
    yr = Y.groupby("yr").r.median(); pos, ny = int((yr > 0).sum()), len(yr)
    ci = boot_ci(Y.groupby("ym").r.mean())
    cit = boot_ci(tr.groupby("ym").r.mean()) if len(tr) >= 25 else np.nan
    trim = Y.r[Y.r <= Y.r.quantile(0.95)].mean()
    ok = (Y.r.median() > 0 and trim > 0 and Y.ex.mean() > 0 and cit == cit and cit > 0
          and ci == ci and ci > 0 and len(va) >= 20 and va.r.median() > 0
          and pos / max(ny, 1) >= 0.6)
    print(f"  {tag:<44}{len(Y):>6}{Y.r.mean():>7.2f}{Y.ex.mean():>7.2f}{Y.r.median():>7.2f}"
          f"{trim:>7.2f}{(Y.r > 0).mean() * 100:>5.0f}%{va.r.median():>8.2f}{cit:>7.2f}{ci:>7.2f}"
          f"{pos:>3}/{ny:<3}{Y.hd.mean():>5.1f}"
          f"{(Y.why == 2).mean() * 100:>5.0f}%{(Y.why == 1).mean() * 100:>5.0f}%"
          + ("  ✅" if ok else ""))
    return Y


HDR = (f"  {'조건':<44}{'n':>6}{'평균':>7}{'초과':>7}{'중앙':>7}{'절삭':>7}{'승률':>6}"
       f"{'검증중앙':>8}{'학CI':>7}{'전CI':>7}{'양수해':>7}{'보유':>5}{'목표':>5}{'손절':>5}")

sec("① 영상 규칙 그대로 — 셋업 × 유니버스 (RRR 1.5 · 최대 10일 · 본전 트레일 있음)")
print(HDR)
NT = 0
for snm, cond in SETUPS:
    for unm, uni in UNIS:
        judge(f"{snm} · {unm}", cond, uni, 1.5, 10, True); NT += 1
    print()

sec("② 손잡이 바꿔보기 — RRR · 보유일 · 본전 트레일 (유니버스: 거래대금 상위10%)")
print(HDR)
_, U10 = UNIS[1]
for snm, cond in SETUPS:
    for rrr in (1.5, 2.0, 3.0):
        for mh in (10, 20):
            for be in (True, False):
                judge(f"{snm} · RRR{rrr} · {mh}일 · 본전{'O' if be else 'X'}",
                      cond, U10, rrr, mh, be); NT += 1
    print()
log(f"시험한 칸 {NT}개")
