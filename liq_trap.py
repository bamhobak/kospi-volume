# -*- coding: utf-8 -*-
"""**유동성 트랩(거짓돌파 역추세) 실측** — 차트트랩 '유동성 매매법' (2026-09-13).

영상 요지: 전고점 위·전저점 아래에는 대기 주문(돌파 매수 · 숏 손절 / 반대도 같음)이 쌓여
있다. 세력이 일부러 그 선을 살짝 뚫어 그 주문을 체결시키고(개미 털기 = 유동성 스윕) 물량을
넘긴 뒤 되돌린다. 그 **거짓 돌파 자리를 반대 방향 진입 타점으로** 쓴다.

지표가 매기는 점수 6요소 중 **마지막 하나는 미래참조**다 — "되돌림 이후 반대 방향으로 얼마나
강하게 갔는지" 는 판정 시점에 아직 일어나지 않은 일이다. 그것을 빼고 **다섯 개**로 잰다.
  ① 돌파 깊이  ② 되돌림(종가가 선 위로 복귀)  ③ 꼬리 길이  ④ 거래량  ⑤ 돌파 직전 눌림(압축)

우리는 공매도를 하지 않으므로 **아래쪽 스윕 → 롱**만 본다(위쪽 스윕은 '회피 신호' 로 확인).
진입은 늘 다음날 시가, 비용 차감. 중복 제거·같은날 유니버스 대비 초과로 판정한다.

    python liq_trap.py [kr|us]
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
from vp_lib import boot_ci

BASE = Path(__file__).parent
MK = (sys.argv[1] if len(sys.argv) > 1 else "kr").lower()
TR1, VA0 = "20221231", "20230101"
HOLDS = (5, 10, 20)
W = 140


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)


log(f"{'us_scan' if MK=='us' else 'kr_scan'}.pkl 읽는 중")
K = pd.read_pickle(BASE / ("data/us_scan.pkl" if MK == "us" else "data/kr_scan.pkl"))
if MK == "us": K = K[((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)]
else:          K = K[((K.close >= 1000) & (~K.pref.fillna(False))).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
ud = sorted(K.date.unique()); K["di"] = K.date.map({d: i for i, d in enumerate(ud)}).astype(np.int32)
JW = (K.jw if "jw" in K.columns else pd.Series(False, index=K.index)).fillna(False)
UNI = (K.groupby("date").amt20.rank(pct=True) >= 0.60).fillna(False)
G = K.groupby("ticker", sort=False)

HAS_OHLC = {"high", "low", "open"} <= set(K.columns)
if not HAS_OHLC:
    # us_scan 에는 고가·저가가 없다. panel_us 에 있으므로 거기서 가져온다.
    # ⚠ 종가 기준이 섞이면 안 되므로 **panel_us 안에서 자체 종가와 함께** 쓰는 것만 넘긴다
    #   (여기서는 open/high/low 를 그대로 붙이되, 스윕 판정에 쓰는 종가도 panel_us 것을 쓴다).
    log("  고가·저가가 없다 — panel_us.pkl 에서 붙인다")
    P = pd.read_pickle(BASE / "data/panel_us.pkl")
    P = P[["ticker", "date", "open", "high", "low", "close"]].rename(columns={"close": "pclose"})
    n0 = len(K)
    K = K.merge(P, on=["ticker", "date"], how="left")
    assert len(K) == n0, "OHLC 병합에서 행이 늘었다 — 키 중복"
    del P
    K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
    HAS_OHLC = True
    CLOSE = K.pclose                       # 스윕 판정은 붙여온 종가로 — 기준을 섞지 않는다
    log(f"  붙음 {K.high.notna().mean()*100:.1f}%")
else:
    CLOSE = K.close

import FinanceDataReader as fdr
IX = fdr.DataReader("US500" if MK == "us" else "KS11", "2004-06-01")
IX = IX[IX.Close > 0].copy(); IX["date"] = IX.index.strftime("%Y%m%d")
IX["ma60"] = IX.Close.rolling(60).mean()
UP = K.date.map(dict(zip(IX.date, IX.Close > IX.ma60))).fillna(False)
log(f"  {len(K):,}행 · 유니버스 {int(UNI.sum()):,}")

# ── 매물대선: 직전 N일 최저/최고 (오늘 제외) ──────────────────────────────
LO, HI = K.low, K.high
for N in (20, 60):
    K[f"lo{N}p"] = LO.groupby(K.ticker).transform(lambda s: s.rolling(N).min()).groupby(K.ticker).shift(1)
    K[f"hi{N}p"] = HI.groupby(K.ticker).transform(lambda s: s.rolling(N).max()).groupby(K.ticker).shift(1)

# 점수 요소
rngv = (HI - LO).replace(0, np.nan)
body_lo = pd.concat([K.open, CLOSE], axis=1).min(axis=1)
body_hi = pd.concat([K.open, CLOSE], axis=1).max(axis=1)
K["wick_dn"] = (body_lo - LO) / rngv
K["wick_up"] = (HI - body_hi) / rngv
K["sq"] = K.vol20.groupby(K.ticker).transform(lambda s: s.rolling(20).mean()).groupby(K.ticker).shift(1)  # 직전 눌림
SQ_Q = K.groupby("date").sq.rank(pct=True)      # 그날 유니버스 안에서 조용한 편인가

BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in HOLDS}
UTRIM = {}
for h in HOLDS:
    u = K[UNI & ~JW].dropna(subset=[f"n{h}"])[f"n{h}"]
    UTRIM[h] = u[u <= u.quantile(0.95)].mean()

NT = 0
HDR = (f"  {'조건':<46}{'n':>7}{'평균':>7}{'초과':>7}{'중앙':>7}{'절삭Δ':>7}{'승률':>6}"
       f"{'검증중앙':>9}{'학CI':>7}{'전CI':>7}{'양수해':>7}")


def judge(tag, cond, h, minn=60, show=True):
    global NT
    NT += 1
    m = (cond & UNI & ~JW).fillna(False)
    X = K[m].dropna(subset=[f"n{h}"]).sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i: continue
        last[t] = i + h; keep.append(ix)
    Y = X.loc[keep]; Y = Y[Y.date >= "20160101"]
    if len(Y) < minn:
        if show: print(f"  {tag:<46}{len(Y):>7} (부족)")
        return None
    Y = Y.copy()
    Y["r"] = Y[f"n{h}"].astype(float); Y["ex"] = Y.r - Y.date.map(BEN[h])
    trim = Y.r[Y.r <= Y.r.quantile(0.95)].mean() - UTRIM[h]
    ym = Y.date.str[:6]; yr = Y.date.str[:4]
    tr = Y.date <= TR1; va = Y.date >= VA0
    ci = boot_ci(Y.ex.groupby(ym).mean())
    cit = boot_ci(Y.ex[tr].groupby(ym[tr]).mean()) if tr.sum() >= 60 else np.nan
    ymed = Y.groupby(yr).r.median(); pos, ny = int((ymed > 0).sum()), len(ymed)
    vam = Y.r[va].median() if va.sum() >= 20 else np.nan
    ok = (Y.r.median() > 0 and trim > 0 and Y.ex.mean() > 0 and ci == ci and ci > 0
          and cit == cit and cit > 0 and vam == vam and vam > 0 and pos / max(ny, 1) >= 0.6)
    if show:
        print(f"  {tag:<46}{len(Y):>7,}{Y.r.mean():>7.2f}{Y.ex.mean():>7.2f}{Y.r.median():>7.2f}"
              f"{trim:>7.2f}{(Y.r > 0).mean() * 100:>5.0f}%{vam:>9.2f}{cit:>7.2f}{ci:>7.2f}"
              f"{pos:>3}/{ny:<3}" + ("  ✅" if ok else ""))
    return Y


# ── 스윕 정의 ─────────────────────────────────────────────────────────
def sweep_dn(N, back):
    """아래쪽 스윕: back 봉 안에 전저점을 뚫었고, **오늘 종가가 그 선 위로** 복귀."""
    lvl = K[f"lo{N}p"]
    pierced = (LO < lvl)
    if back > 1:
        pierced = pierced.groupby(K.ticker).transform(lambda s: s.rolling(back).max().astype(bool))
    return (pierced & (CLOSE > lvl)).fillna(False)


def sweep_up(N, back):
    lvl = K[f"hi{N}p"]
    pierced = (HI > lvl)
    if back > 1:
        pierced = pierced.groupby(K.ticker).transform(lambda s: s.rolling(back).max().astype(bool))
    return (pierced & (CLOSE < lvl)).fillna(False)


sec(f"① 아래쪽 스윕 → 롱 — {'미장' if MK=='us' else '국내'} · 기본형")
print("  '전저점을 뚫었다가 종가가 그 위로 복귀' 만. 점수 조건 없음.")
print(HDR)
for N in (20, 60):
    for back in (1, 2, 3):
        c = sweep_dn(N, back)
        for h in HOLDS:
            judge(f"전저점{N}일 · {back}봉 안 복귀 · {h}일 보유", c, h)
    print()

sec("② 점수 요소 얹기 (전저점 20일 · 1봉 복귀 · 10일 보유 기준)")
print(HDR)
base = sweep_dn(20, 1)
lvl20 = K["lo20p"]
depth = ((lvl20 - LO) / lvl20 * 100)
ADD = [("기준(아무 조건 없음)", pd.Series(True, index=K.index)),
       ("① 깊이 ≥1% 뚫음", depth >= 1), ("① 깊이 ≥3% 뚫음", depth >= 3),
       ("② 종가가 선 위 +2% 이상", CLOSE >= lvl20 * 1.02),
       ("③ 아래꼬리 ≥ 몸통범위 50%", K.wick_dn >= 0.5),
       ("③ 아래꼬리 ≥ 70%", K.wick_dn >= 0.7),
       ("④ 거래량 1.5배", K.su1 >= 1.5), ("④ 거래량 2배", K.su1 >= 2),
       ("⑤ 직전 눌림(변동성 하위40%)", SQ_Q <= 0.4),
       ("⑤ 직전 눌림(하위20%)", SQ_Q <= 0.2)]
for nm, c in ADD:
    judge(f"스윕 + {nm}", base & c.fillna(False), 10)

sec("③ 국면 게이트 (전저점 20일 · 1봉 복귀)")
print(HDR)
for gn, g in (("상승장(지수 60일선 위)", UP), ("하락장(지수 60일선 아래)", ~UP)):
    for h in HOLDS:
        judge(f"스윕 · {gn} · {h}일 보유", base & g, h)
    print()

sec("④ 위쪽 스윕은 정말 나쁜가 (숏 대신 '사지 마라' 로 확인)")
print(HDR)
for N in (20, 60):
    cu = sweep_up(N, 1)
    for h in HOLDS:
        judge(f"위쪽 스윕(전고점{N}일) · {h}일 보유 — 음수여야 맞다", cu, h)
    print()

log(f"시험한 칸 {NT}개")
