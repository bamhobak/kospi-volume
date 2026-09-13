# -*- coding: utf-8 -*-
"""**전일 고가·저가 돌파 후 재확인(break and retest)** 실측 — Jdub Trades (2026-09-14).

영상('My Trading Strategy Is Boring, But It Makes Me $44,000/Month')의 뼈대는 **break and
retest** 이고 셋업이 셋이다.
  ① 개장 첫 캔들(opening range) 돌파·재확인   ② 오더블록   ③ **전일 고가·저가 돌파·재확인**

①②는 **장중(1~5분봉) 자료가 있어야** 한다 — 우리에겐 일봉뿐이라 못 잰다. 지어내지 않는다.
③만 일봉으로 옮길 수 있다. 어제 잰 [유동성 스윕]은 **60일** 고저를 썼는데 여기는 **전일**
고저다 — 훨씬 짧은 레벨이라 따로 잴 가치가 있다.

  A 전일고가 돌파 후 되돌림 지지 → 롱 (continuation)
  B 전일저가 이탈 후 종가 복귀 → 롱 (reversal · 어제 스윕의 1일판)
  C 전일고가 단순 돌파 → 롱 (재확인 없이 · 대조군)
  D 전일저가 지지(이탈 없이 닿기만) → 롱

⚠ 영상은 손절 타이트·RRR 1:2 로 장중에 끝낸다. 일봉에서는 그 청산을 재현할 수 없으므로
   **우리 청산(정해진 날 종가)** 으로 재고, 셋업 자체에 선별력이 있는지만 본다.

    python pdh_retest.py [kr|us]
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
W = 138


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)


log(f"{'us_scan' if MK=='us' else 'kr_scan'}.pkl 읽는 중")
K = pd.read_pickle(BASE / ("data/us_scan.pkl" if MK == "us" else "data/kr_scan.pkl"))
if MK == "us": K = K[((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)]
else:          K = K[((K.close >= 1000) & (~K.pref.fillna(False))).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
if MK == "us":
    log("panel_us.pkl 에서 OHLC 붙이는 중")
    P = pd.read_pickle(BASE / "data/panel_us.pkl")[["ticker", "date", "open", "high", "low", "close"]]
    P = P.rename(columns={"close": "pclose"})
    n0 = len(K); K = K.merge(P, on=["ticker", "date"], how="left"); del P
    assert len(K) == n0
    K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
    CLOSE = K.pclose
else:
    CLOSE = K.close
ud = sorted(K.date.unique()); K["di"] = K.date.map({d: i for i, d in enumerate(ud)}).astype(np.int32)
JW = (K.jw if "jw" in K.columns else pd.Series(False, index=K.index)).fillna(False)
UNI = (K.groupby("date").amt20.rank(pct=True) >= 0.60).fillna(False)
G = K.groupby("ticker", sort=False)
import FinanceDataReader as fdr
IX = fdr.DataReader("US500" if MK == "us" else "KS11", "2004-06-01")
IX = IX[IX.Close > 0].copy(); IX["date"] = IX.index.strftime("%Y%m%d")
IX["ma60"] = IX.Close.rolling(60).mean()
UP = K.date.map(dict(zip(IX.date, IX.Close > IX.ma60))).fillna(False)
log(f"  {len(K):,}행 · 유니버스 {int(UNI.sum()):,}")

PDH = G.high.shift(1)          # 전일 고가
PDL = G.low.shift(1)           # 전일 저가
PDH2 = G.high.shift(2)         # 그제 고가 (어제의 '전일고가')
PDL2 = G.low.shift(2)
Cy = CLOSE.groupby(K.ticker).shift(1)

BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in HOLDS}
UTRIM = {}
for h in HOLDS:
    u = K[UNI & ~JW].dropna(subset=[f"n{h}"])[f"n{h}"]
    UTRIM[h] = u[u <= u.quantile(0.95)].mean()
NT = 0
HDR = (f"  {'조건':<44}{'n':>8}{'평균':>7}{'초과':>7}{'중앙':>7}{'절삭Δ':>7}{'승률':>6}"
       f"{'검증중앙':>9}{'학CI':>7}{'전CI':>7}{'양수해':>7}")


def judge(tag, cond, h, minn=80, show=True):
    global NT
    NT += 1
    X = K[(cond & UNI & ~JW).fillna(False)].dropna(subset=[f"n{h}"]).sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i: continue
        last[t] = i + h; keep.append(ix)
    Y = X.loc[keep]; Y = Y[Y.date >= "20160101"]
    if len(Y) < minn:
        if show: print(f"  {tag:<44}{len(Y):>8} (부족)")
        return None
    Y = Y.copy()
    Y["r"] = Y[f"n{h}"].astype(float); Y["ex"] = Y.r - Y.date.map(BEN[h])
    trim = Y.r[Y.r <= Y.r.quantile(0.95)].mean() - UTRIM[h]
    ym = Y.date.str[:6]; yr = Y.date.str[:4]
    tr = Y.date <= TR1; va = Y.date >= VA0
    ci = boot_ci(Y.ex.groupby(ym).mean())
    cit = boot_ci(Y.ex[tr].groupby(ym[tr]).mean()) if tr.sum() >= 60 else np.nan
    ymed = Y.groupby(yr).r.median(); pos, ny = int((ymed > 0).sum()), len(ymed)
    vam = Y.r[va].median() if va.sum() >= 30 else np.nan
    ok = (Y.r.median() > 0 and trim > 0 and Y.ex.mean() > 0 and ci == ci and ci > 0
          and cit == cit and cit > 0 and vam == vam and vam > 0 and pos / max(ny, 1) >= 0.6)
    if show:
        print(f"  {tag:<44}{len(Y):>8,}{Y.r.mean():>7.2f}{Y.ex.mean():>7.2f}{Y.r.median():>7.2f}"
              f"{trim:>7.2f}{(Y.r > 0).mean()*100:>5.0f}%{vam:>9.2f}{cit:>7.2f}{ci:>7.2f}"
              f"{pos:>3}/{ny:<3}" + ("  ✅" if ok else ""))
    return Y


# ── 셋업 ─────────────────────────────────────────────────────────────
A = ((Cy > PDH2) & (K.low <= PDH2) & (CLOSE > PDH2)).fillna(False)   # 어제 돌파 → 오늘 되돌림 지지
B = ((K.low < PDL) & (CLOSE > PDL)).fillna(False)                    # 전일저가 이탈 후 복귀
C = (CLOSE > PDH).fillna(False)                                      # 단순 돌파(대조군)
D = ((K.low <= PDL) & (K.low >= PDL * 0.99) & (CLOSE > PDL)).fillna(False)  # 전일저가 닿고 지지
SET = [("A 전일고가 돌파→되돌림 지지", A), ("B 전일저가 이탈→종가 복귀", B),
       ("C 전일고가 단순 돌파(대조군)", C), ("D 전일저가 닿고 지지", D)]

sec(f"① 네 셋업 — {'미장' if MK=='us' else '국내'} · 국면 무관")
print(HDR)
for nm, c in SET:
    for h in HOLDS:
        judge(f"{nm} · {h}일 보유", c, h)
    print()

sec("② 국면 게이트 (영상은 '상위 시간대 추세와 같은 방향' 을 요구한다)")
print(HDR)
for nm, c in SET[:2]:
    for gn, g in (("상승장", UP), ("하락장", ~UP)):
        for h in (5, 10):
            judge(f"{nm} · {gn} · {h}일", c & g, h)
    print()

sec("③ 조이기 — 돌파 강도·거래량 (영상의 'displacement' 와 같은 뜻)")
print(HDR)
for nm, c in (("A", A), ("B", B)):
    base = A if nm == "A" else B
    lvl = PDH2 if nm == "A" else PDL
    for tag, x in (("그대로", pd.Series(True, index=K.index)),
                   ("거래량 1.5배", K.su1 >= 1.5), ("거래량 2배", K.su1 >= 2),
                   ("종가가 레벨 위 +1%↑", CLOSE >= lvl * 1.01),
                   ("종가가 레벨 위 +3%↑", CLOSE >= lvl * 1.03)):
        judge(f"{nm} + {tag} · 10일", base & x.fillna(False), 10)
    print()
log(f"시험한 칸 {NT}개")
