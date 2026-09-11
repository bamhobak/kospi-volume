# -*- coding: utf-8 -*-
"""ICT(스마트머니) 3종을 국내 패널에 대입한다 — 하백남 「볼린저밴드 RSI MACD는 다 버리세요」
(2026-09-12 사용자 링크 · youtu.be/SME-n0PK2BQ).

영상이 말하는 것은 셋뿐이고 전부 일봉 OHLC 로 계산된다:
  ① **BOS**(Break of Structure) — 직전 스윙 고점을 돌파하면 추세가 이어진다
  ② **CHoCH**(Change of Character) — 직전 스윙 저점을 **몸통으로** 이탈하면 추세가 뒤집힌다.
     영상의 핵심 주장이 '꼬리가 아니라 몸통' 이므로 **꼬리만 이탈한 경우를 대조군으로 둔다.**
  ③ **FVG**(Fair Value Gap) — 3봉 사이에 생긴 갭. CHoCH 가 FVG 를 동반하면 확정이라 한다.
  길이값은 영상이 쓴 **11(중기·일봉)** 과 **7(단기)** 두 가지.

⚠ 선행참조 금지: 스윙 고점은 그 뒤 L 봉이 지나야 확정된다. 그래서 i-L 자리의 피봇을
  **i 에서야** 알 수 있는 것으로 처리한다. 이걸 안 지키면 미래를 보고 사는 셈이 된다.

기대치는 낮다. BOS 는 본질적으로 돌파 추격이라 [[community-techniques]] 의 Donchian
신고가(초과 -0.3 · 연양수 0/11)와 같은 축이고, [[invert-test]] 의 '급등 추격은 회피 신호'
와도 겹친다. 다만 **CHoCH 는 낙폭 반전 계열**이라 국내에서 볼 여지가 있다.

    python ict_kr.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
from vp_lib import boot_ci

BASE = Path(__file__).parent
TR1, VA0 = "20221231", "20230101"
HOLDS = (5, 10, 20, 40, 60)
LENS = (7, 11)


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


log("kr_scan.pkl 읽는 중")
K = pd.read_pickle(BASE / "data/kr_scan.pkl")
# 폐지 위험 방어(우리 집 기준)와 우선주 제외
K = K[((K.close >= 1000) & (~K.pref.fillna(False))).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
ud = sorted(K.date.unique())
K["di"] = K.date.map({d: i for i, d in enumerate(ud)}).astype(np.int32)
UNI = (K.groupby("date").amt20.rank(pct=True) >= 0.6).fillna(False)
log(f"준비 {len(K):,}행 · {K.ticker.nunique():,}종목 · {K.date.min()}~{K.date.max()}")


def pivots(g, L):
    """확정된 직전 스윙 고점·저점 값과 그 이전 값. 전부 '오늘 알 수 있는' 값만 쓴다."""
    hi, lo = g["high"], g["low"]
    w = 2 * L + 1
    # i-L 자리가 창 [i-2L, i] 의 최고(최저)면 피봇 — 그 판정은 i 에서야 가능하다
    ph = hi.shift(L).where(hi.shift(L) == hi.rolling(w).max())
    pl = lo.shift(L).where(lo.shift(L) == lo.rolling(w).min())
    out = {}
    for nm, s in (("sh", ph), ("sl", pl)):
        cur = s.ffill()                      # 직전 확정 피봇
        prv = s.copy()
        m = prv.notna()
        prv[m] = prv[m].shift()              # 그 이전 피봇
        out[nm] = cur
        out[nm + "p"] = prv.ffill()
    return out


log("스윙 구조 계산 중 (길이 7·11)")
t0 = time.time()
cols = {f"{k}{L}": np.full(len(K), np.nan) for L in LENS for k in ("sh", "shp", "sl", "slp")}
for _, g in K.groupby("ticker", sort=False):
    idx = g.index.values
    for L in LENS:
        p = pivots(g, L)
        for k in ("sh", "shp", "sl", "slp"):
            cols[f"{k}{L}"][idx] = p[k].values
for k, v in cols.items():
    K[k] = v
log(f"  완료 {time.time()-t0:.0f}초")

# FVG — 3봉 갭. 상승: 오늘 저가가 이틀 전 고가보다 높다 / 하락: 오늘 고가가 이틀 전 저가보다 낮다
G = K.groupby("ticker", sort=False)
K["fvgU"] = (K.low > G.high.shift(2)).fillna(False)
K["fvgD"] = (K.high < G.low.shift(2)).fillna(False)
# 최근 3봉 안에 상승 FVG 가 있었나 (영상은 '이탈 구간에 FVG 가 발생' 이라고만 한다)
K["fvgU3"] = (K.fvgU | G.fvgU.shift(1).fillna(False) | G.fvgU.shift(2).fillna(False))

BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in HOLDS}
NDAY = len([d for d in ud if d >= "20160101"])


def trim(r):
    r = pd.Series(r).dropna()
    return r[r <= r.quantile(0.95)].mean() if len(r) else np.nan


BT = {h: trim(K[UNI & (K.date >= "20160101")][f"n{h}"].dropna().astype(float)) for h in HOLDS}
log("유니버스 절삭평균 " + " ".join(f"{h}일 {BT[h]:+.2f}" for h in HOLDS))


def dd(cond, h, lo="20160101", hi="20991231"):
    X = K[(cond & UNI).fillna(False)].dropna(subset=[f"n{h}"])
    X = X[(X.date >= lo) & (X.date <= hi)].sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i + h; keep.append(ix)
    d = X.loc[keep].copy()
    d["r"] = d[f"n{h}"].astype(float)
    d["ex"] = d.r - d.date.map(BEN[h])
    d["ym"] = d.date.str[:6]
    return d[d.r.notna()]


HDR = (f"  {'조건':<34}{'n':>8}{'동시':>6}{'승률':>7}{'중앙':>8}{'절삭Δ':>8}"
       f"{'초과':>8}{'학습':>8}{'검증':>8}{'CI':>8}{'연양수':>8}")
OK = []


def show(tag, cond, h):
    d = dd(cond, h)
    if len(d) < 80:
        print(f"  {tag:<34}{len(d):>8}  (표본 부족)"); return None
    yr = d.groupby(d.date.str[:4]).ex.mean()
    ci = boot_ci(d.groupby("ym").ex.mean())
    dtm = trim(d.r) - BT[h]
    per = len(d) / NDAY
    print(f"  {tag:<34}{len(d):>8,}{per*h:>6.0f}{(d.r>0).mean()*100:>6.1f}%{d.r.median():>8.2f}"
          f"{dtm:>8.2f}{d.ex.mean():>8.2f}{d[d.date<=TR1].ex.mean():>8.2f}"
          f"{d[d.date>=VA0].ex.mean():>8.2f}{ci:>8.2f}{int((yr>0).sum()):>5}/{len(yr)}")
    if (dtm > 0 and d.ex.mean() > 0 and d[d.date >= VA0].ex.mean() > 0
            and ci > 0 and (yr > 0).sum() >= len(yr) * 0.72):
        OK.append((tag, h, len(d), d.ex.mean(), ci, int((yr > 0).sum()), len(yr)))
    return d


def ev(c):
    s = pd.Series(c.values, index=K.index, name="_c")
    K["_c"] = s
    out = s & ~K.groupby("ticker", sort=False)["_c"].shift(1).fillna(False)
    return out


W = 148
for L in LENS:
    sh, shp, sl, slp = K[f"sh{L}"], K[f"shp{L}"], K[f"sl{L}"], K[f"slp{L}"]
    upstruct = (sh > shp) & (sl > slp)          # HH & HL
    dnstruct = (sh < shp) & (sl < slp)          # LH & LL
    # '몸통으로 이탈' = 종가가 선을 넘는 것. 종가가 곧 몸통의 한쪽 경계라서 따로 만들 게 없다.
    # 꼬리만 넘은 경우는 아래 wick_up 이 대조군으로 잡는다.
    over_sh = K.close > sh
    under_sl = K.close < sl

    bos_up = ev(over_sh & upstruct)                     # 추세 지속 돌파
    choch_up = ev(over_sh & dnstruct)                   # 추세 전환 돌파(몸통)
    wick_up = ev((K.high > sh) & (K.close <= sh) & dnstruct)   # 꼬리만 — 대조군
    choch_dn = ev(under_sl & upstruct)                  # 상승 중 저점 이탈(영상의 매도 신호)
    bos_dn = ev(under_sl & dnstruct)

    print("\n" + "=" * W)
    print(f"길이값 {L} · 보유별 — 매수 신호 후보 (국내 · 2016~ · 거래대금 상위 40%)")
    print("=" * W); print(HDR)
    for h in HOLDS:
        show(f"  BOS↑ 지속돌파 · {h}일", bos_up, h)
    print()
    for h in HOLDS:
        show(f"  CHoCH↑ 전환돌파(몸통) · {h}일", choch_up, h)
    print()
    print("  ── 영상의 핵심 주장 검증: 몸통 이탈 vs 꼬리만 (같은 조건·같은 보유) ──")
    for h in (20, 60):
        show(f"  CHoCH↑ 몸통 · {h}일", choch_up, h)
        show(f"  꼬리만(대조군) · {h}일", wick_up, h)
    print()
    print("  ── FVG 동반이 확정인가 ──")
    for h in (20, 60):
        show(f"  CHoCH↑ + FVG · {h}일", choch_up & K.fvgU3, h)
        show(f"  CHoCH↑ · FVG 없음 · {h}일", choch_up & ~K.fvgU3, h)
    print()
    print("  ── 영상이 '매도' 라 한 쪽 — 사면 정말 나쁜가(회피 신호 여부) ──")
    for h in (20, 60):
        show(f"  CHoCH↓ 상승중 저점이탈 · {h}일", choch_dn, h)
        show(f"  BOS↓ 하락 지속 · {h}일", bos_dn, h)

print("\n" + "=" * W)
print("집안 잣대 통과 (절삭Δ>0 · 초과>0 · 검증>0 · CI>0 · 연양수 72%↑)")
print("=" * W)
if OK:
    for t, h, n, ex, ci, y, ny in OK:
        print(f"  ✅ {t.strip():<36}{h:>3}일 · {n:>7,}건 · 초과 {ex:+.2f} · CI {ci:+.2f} · 양수해 {y}/{ny}")
else:
    print("  통과 없음")
try:
    import verdict
    print("\n누적 시행:", verdict.log_trials("ict_haebaeknam", 2 * len(LENS) * (len(HOLDS) * 2 + 8)))
except Exception as e:
    print(e)
