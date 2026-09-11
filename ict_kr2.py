# -*- coding: utf-8 -*-
"""ict_kr.py 에서 유일하게 통과한 **BOS↓**(하락 추세에서 직전 저점을 다시 깬 날 매수)를 캔다.

영상은 이걸 '하락 지속이니 팔아라' 로 쓰는데, 국내에서 **사면** 집안 잣대를 통과했다
(길이 7 · 20일 초과 +4.22 · 60일 +7.22 · 연양수 9/11). 믿기 전에 넷을 본다.

  ① **중앙값을 유니버스와 견준다** — ict_kr.py 는 절삭평균만 유니버스와 견주고 중앙값은
     0 과 견줬다. 국내 유니버스는 중앙값 자체가 크게 음수라 0 과 견주면 뭐든 나빠 보인다.
  ② **길이값 이웃(5~13)** — 7 은 통과하고 11 은 떨어졌다. 7 한 칸만 좋으면 노이즈다
     ([[community-techniques]] 50일선 교훈).
  ③ **연도별·시대별** — 학습 +12.20 → 검증 +0.16 로 거의 사라졌다. 한두 해 쏠림인가.
  ④ **기존 하락장 규칙과의 겹침** — 결국 '많이 떨어진 걸 산다' 라 [폭락 반등]·[낙폭과대]와
     같은 축일 수 있다. 같은 날 같은 종목을 얼마나 집는지 센다. 많이 겹치면 새 규칙이
     아니라 자리만 나눠 먹는다([[rule-relations]]).

    python ict_kr2.py
"""
import sys, math, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
from vp_lib import boot_ci

BASE = Path(__file__).parent
TR1, VA0 = "20221231", "20230101"
LENS = (5, 6, 7, 8, 9, 11, 13)
HOLDS = (20, 60)


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


log("kr_scan.pkl 읽는 중")
K = pd.read_pickle(BASE / "data/kr_scan.pkl")
K = K[((K.close >= 1000) & (~K.pref.fillna(False))).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
ud = sorted(K.date.unique())
K["di"] = K.date.map({d: i for i, d in enumerate(ud)}).astype(np.int32)
UNI = (K.groupby("date").amt20.rank(pct=True) >= 0.6).fillna(False)
log(f"준비 {len(K):,}행 · {K.ticker.nunique():,}종목")

log(f"스윙 구조 계산 중 (길이 {LENS})")
t0 = time.time()
cols = {f"{k}{L}": np.full(len(K), np.nan) for L in LENS for k in ("sl", "slp")}
for _, g in K.groupby("ticker", sort=False):
    idx = g.index.values
    lo = g["low"]
    for L in LENS:
        pl = lo.shift(L).where(lo.shift(L) == lo.rolling(2 * L + 1).min())
        cur = pl.ffill()
        prv = pl.copy(); m = prv.notna(); prv[m] = prv[m].shift()
        cols[f"sl{L}"][idx] = cur.values
        cols[f"slp{L}"][idx] = prv.ffill().values
for k, v in cols.items():
    K[k] = v
log(f"  완료 {time.time()-t0:.0f}초")

BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in HOLDS}
NDAY = len([d for d in ud if d >= "20160101"])


def trim(r):
    r = pd.Series(r).dropna()
    return r[r <= r.quantile(0.95)].mean() if len(r) else np.nan


# ── ① 유니버스 기준선: 절삭평균과 **중앙값** 을 함께 둔다 ───────────────────────────
BT, BM = {}, {}
for h in HOLDS:
    u = K[UNI & (K.date >= "20160101")][f"n{h}"].dropna().astype(float)
    BT[h] = trim(u); BM[h] = float(u.median())
log("유니버스 기준선 " + " ".join(f"{h}일 절삭 {BT[h]:+.2f}·중앙 {BM[h]:+.2f}" for h in HOLDS))


def ev(c):
    K["_c"] = pd.Series(np.asarray(c), index=K.index)
    return K["_c"] & ~K.groupby("ticker", sort=False)["_c"].shift(1).fillna(False)


def bosdn(L):
    """하락 구조(LL)에서 직전 확정 스윙 저점을 종가로 다시 깬 첫날"""
    sl, slp = K[f"sl{L}"], K[f"slp{L}"]
    return ev((K.close < sl) & (sl < slp))


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


W = 140
print("\n" + "=" * W)
print("① + ② 길이값 이웃 — 7 만 좋은가, 넓게 좋은가 (중앙값도 유니버스와 견준다)")
print("=" * W)
print(f"  {'길이':>5}{'보유':>5}{'n':>8}{'동시':>6}{'승률':>7}{'중앙Δ':>8}{'절삭Δ':>8}"
      f"{'초과':>8}{'학습':>8}{'검증':>8}{'CI':>8}{'연양수':>8}")
SER = {}
for L in LENS:
    c = bosdn(L)
    for h in HOLDS:
        d = dd(c, h); SER[(L, h)] = d
        if len(d) < 80:
            print(f"  {L:>5}{h:>5}{len(d):>8}  (부족)"); continue
        yr = d.groupby(d.date.str[:4]).ex.mean()
        print(f"  {L:>5}{h:>5}{len(d):>8,}{len(d)/NDAY*h:>6.0f}{(d.r>0).mean()*100:>6.1f}%"
              f"{d.r.median()-BM[h]:>8.2f}{trim(d.r)-BT[h]:>8.2f}{d.ex.mean():>8.2f}"
              f"{d[d.date<=TR1].ex.mean():>8.2f}{d[d.date>=VA0].ex.mean():>8.2f}"
              f"{boot_ci(d.groupby('ym').ex.mean()):>8.2f}{int((yr>0).sum()):>5}/{len(yr)}")
    print()
print("  → 이웃이 함께 좋으면 고원(진짜), 7 만 튀면 봉우리(노이즈)다.")

print("\n" + "=" * W)
print("③ 연도별 — 한두 해가 다 만든 것인가 (길이 7)")
print("=" * W)
for h in HOLDS:
    d = SER[(7, h)]
    t = d.groupby(d.date.str[:4]).agg(n=("r", "size"), x=("ex", "mean"))
    print(f"  [{h}일] " + " · ".join(f"{y} {r.x:+.1f}({int(r.n)})" for y, r in t.iterrows()))
    top = t.x.idxmax()
    e = d[d.date.str[:4] != top]
    print(f"    최고해 {top} 빼면 초과 {d.ex.mean():+.2f} → {e.ex.mean():+.2f}"
          f" · CI {boot_ci(e.groupby('ym').ex.mean()):+.2f}")
    for lo, hi, nm in (("20050101", "20151231", "스트레스 2005~15"),
                       ("20160101", "20221231", "학습 2016~22"),
                       ("20230101", "20991231", "검증 2023~26")):
        s = dd(bosdn(7), h, lo, hi)
        if len(s) >= 80:
            print(f"    {nm:<16} {len(s):>6,}건 · 초과 {s.ex.mean():+.2f} · 중앙Δ {s.r.median()-BM[h]:+.2f}"
                  f" · 절삭Δ {trim(s.r)-BT[h]:+.2f}")
    print()

print("\n" + "=" * W)
print("④ 기존 하락장 규칙과 겹치는가 — 새 규칙인가, 이미 가진 것인가")
print("=" * W)
# 집 규칙을 그대로 쓰기는 무거우니 '많이 떨어진 자리' 를 대표하는 조건들과 견준다
PROX = {
    "낙폭과대(52주고점 -30%↓)": (K.fromhi <= -30),
    "폭락반등(20일 -25%↓)": (K.ret20 <= -25),
    "깊은이격(25일선 -25%↓)": (K.dev25 <= -25),
    "단순 하락(60일 수익 음수)": (K.ret60 < 0),
}
for h in HOLDS:
    d = SER[(7, h)]
    key = set(zip(d.date.values, d.ticker.values))
    print(f"  [{h}일] BOS↓ 신호 {len(key):,}건 중")
    for nm, cond in PROX.items():
        m = cond.reindex(d.index).fillna(False).values
        print(f"    {nm:<26} 동시 성립 {m.sum():>6,}건 ({m.mean()*100:>5.1f}%)"
              f" · 그 안 초과 {d[m].ex.mean():+.2f} · 나머지 {d[~m].ex.mean():+.2f}")
    print()

print("\n" + "=" * W)
print("정식 판정 (길이 7 · 다중검정 보정)")
print("=" * W)
try:
    import verdict
    for h in HOLDS:
        d = SER[(7, h)]
        yr = d.groupby(d.date.str[:4]).ex.mean()
        verdict.judge(f"ICT BOS↓ 매수 · 길이7 · {h}일 (2016~)", d.groupby("ym").ex.mean(),
                      topic="ict_haebaeknam", median=d.r.median(), last_year=yr.get("2026"))
except Exception as e:
    print(e)
