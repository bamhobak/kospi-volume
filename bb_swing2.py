# -*- coding: utf-8 -*-
"""Booming Bulls 스윙 매매법 2단계 — 셋업이 죽은 건가, 청산이 죽인 건가 (2026-09-12).

bb_swing.py 에서 60칸 전부 기각됐다. 그런데 **초과수익이 0 근처**였다(-0.4 ~ +0.2).
즉 셋업이 고른 종목이 유니버스보다 나쁘지 않았는데 **절대수익만 음수**였다.
그러면 까먹은 것은 셋업이 아니라 **청산(손절·목표)** 이다. 이걸 가른다.

  ① 같은 셋업 · **우리 집 청산**(손절 없음 · 정해진 날 종가) — 셋업에 선별력이 있나
  ② 청산만 바꾼 짝비교 — 손절이 얼마를 까먹나
  ③ 국면 게이트 · 우리 재료 얹기 — 살릴 구석이 있나
  ④ 다중검정 보정

    python bb_swing2.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
from vp_lib import boot_ci

BASE = Path(__file__).parent
TR1, VA0 = "20221231", "20230101"
W = 148


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
AR = K.groupby("date").amt20.rank(pct=True)
UNI = (AR >= 0.60).fillna(False)          # 집안 기준
U10 = (AR >= 0.90).fillna(False)          # 영상의 Nifty100 급

log("셋업 계산 중")
K["hi60p"] = G.high.transform(lambda s: s.rolling(60).max()).groupby(K.ticker).shift(1)
K["green"] = (K.close > K.open).fillna(False)
BRK = (K.close > K.hi60p).fillna(False)
K["lvl"] = K.hi60p.where(BRK).groupby(K.ticker).ffill()
K["agebrk"] = K.di - K.di.where(BRK).groupby(K.ticker).ffill()
RT = ((K.agebrk.between(1, 20)) & (K.low <= K.lvl * 1.03) & (K.close >= K.lvl * 0.99) & K.green).fillna(False)
L = 7; w = 2 * L + 1
ph = G.high.transform(lambda s: s.shift(L).where(s.shift(L) == s.rolling(w).max()))
pl = G.low.transform(lambda s: s.shift(L).where(s.shift(L) == s.rolling(w).min()))
K["sh"] = ph.groupby(K.ticker).ffill(); K["sl"] = pl.groupby(K.ticker).ffill()
leg = K.sh - K.sl
GOLD = ((leg > 0) & (K.sh > K.sl * 1.10) & (K.low <= K.sh - leg * 0.382)
        & (K.low >= (K.sh - leg * 0.618) * 0.98) & (K.close > K.sh - leg * 0.618) & K.green).fillna(False)
SETUPS = [("① 돌파", BRK & K.green), ("② 돌파 후 재확인", RT),
          ("③ 황금구간 되돌림", GOLD), ("②+③ 되돌림 계열", RT | GOLD)]

# 국면 — 코스피 60일선
IX = K.groupby("date").close.median(); IXMA = IX.rolling(60).mean()
DN60 = K.date.map(IX < IXMA).fillna(False)
UP60 = K.date.map(IX >= IXMA).fillna(False)

HOLDS = (5, 10, 20)
BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in HOLDS}
HDR = (f"  {'조건':<42}{'n':>7}{'평균':>7}{'초과':>7}{'중앙':>7}{'절삭Δ':>7}{'승률':>6}"
       f"{'학중앙':>7}{'검중앙':>7}{'학CI':>7}{'전CI':>7}{'양수해':>7}")
NT = 0


def judge(tag, cond, uni, h, minn=40, show=True):
    global NT
    NT += 1
    m = (cond & uni & ~JW).fillna(False)
    X = K[m].dropna(subset=[f"n{h}"]).sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i: continue
        last[t] = i + h; keep.append(ix)
    Y = X.loc[keep].copy()
    Y = Y[Y.date >= "20160101"]
    if len(Y) < minn:
        if show: print(f"  {tag:<42}{len(Y):>7} (부족)")
        return None
    Y["r"] = Y[f"n{h}"].astype(float); Y["ex"] = Y.r - Y.date.map(BEN[h])
    Y["yr"] = Y.date.str[:4]; Y["ym"] = Y.date.str[:6]
    U = K[uni & ~JW].dropna(subset=[f"n{h}"])
    ut = U[f"n{h}"]; utrim = ut[ut <= ut.quantile(0.95)].mean()
    trim = Y.r[Y.r <= Y.r.quantile(0.95)].mean()
    tr = Y[Y.date <= TR1]; va = Y[Y.date >= VA0]
    yr = Y.groupby("yr").r.median(); pos, ny = int((yr > 0).sum()), len(yr)
    ci = boot_ci(Y.groupby("ym").ex.mean())
    cit = boot_ci(tr.groupby("ym").ex.mean()) if len(tr) >= 25 else np.nan
    ok = (Y.r.median() > 0 and (trim - utrim) > 0 and Y.ex.mean() > 0 and cit == cit and cit > 0
          and ci == ci and ci > 0 and len(va) >= 20 and va.r.median() > 0 and pos / max(ny, 1) >= 0.6)
    if show:
        print(f"  {tag:<42}{len(Y):>7}{Y.r.mean():>7.2f}{Y.ex.mean():>7.2f}{Y.r.median():>7.2f}"
              f"{trim - utrim:>7.2f}{(Y.r > 0).mean() * 100:>5.0f}%{tr.r.median():>7.2f}{va.r.median():>7.2f}"
              f"{cit:>7.2f}{ci:>7.2f}{pos:>3}/{ny:<3}" + ("  ✅" if ok else ""))
    return Y


sec("① 같은 셋업 · 우리 집 청산(손절 없음 · 정해진 날 종가 매도) — 셋업에 선별력이 있나")
print(HDR)
for snm, cond in SETUPS:
    for h in HOLDS:
        judge(f"{snm} · {h}일 보유 · 상위40%", cond, UNI, h)
    print()

sec("② 유니버스를 영상대로 좁히면 (거래대금 상위10% = Nifty100 급)")
print(HDR)
for snm, cond in SETUPS:
    for h in HOLDS:
        judge(f"{snm} · {h}일 보유 · 상위10%", cond, U10, h)
    print()

sec("③ 국면 게이트 · 우리 재료 얹기 (되돌림 계열 · 10일)")
print(HDR)
RET = RT | GOLD
EX = [("국면 없음(기준)", pd.Series(True, index=K.index)),
      ("상승장만(코스피 60일선 위)", UP60),
      ("하락장만(코스피 60일선 아래)", DN60)]
for nm, g in EX:
    judge(f"되돌림 · {nm}", RET & g, UNI, 10)
print()
# kr_scan.pkl 에 있는 재료만 쓴다(수급 열은 panel_kp/kq 에만 있다)
MAT = [("거래량 2배(su1≥2)", K.su1 >= 2), ("거래량 3배(su1≥3)", K.su1 >= 3),
       ("공매도 감소(srd)", K.srd == True), ("저PBR ≤0.8", (K.PBR > 0) & (K.PBR <= 0.8)),
       ("희석 공시 없음", ~K.dil.fillna(False)),
       ("낙폭 20일 ≤-10%", K.ret20 <= -10), ("낙폭 20일 ≤-20%", K.ret20 <= -20),
       ("고점대비 -30%↓", K.fromhi <= -30), ("1년수익 >0", K.ret250 > 0)]
for nm, c in MAT:
    if not hasattr(c, "fillna"): continue
    judge(f"되돌림 + {nm}", RET & c.fillna(False), UNI, 10)

sec("④ 판정")
print(f"  시험한 칸 {NT}개 (bb_swing.py 60칸 + 여기 {NT}칸)")
try:
    from verdict import log_trials
    log_trials("booming_bulls", 60 + NT)
    print("  trials.json 에 기록했다")
except Exception as e:
    print(f"  trials 기록 실패: {e!r}")
