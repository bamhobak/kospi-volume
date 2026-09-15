# -*- coding: utf-8 -*-
"""**「기대감에 오르고 뚜껑 열리면 빠진다」를 데이터로** + N6 조이기 (2026-09-15 요청).

사용자 지적: "게임이나 제품이 나오기 한참 전에 기대감으로 오르고, 막상 출시되면 떨어지는
경우가 많잖아." — 이른바 buy the rumor, sell the news 다.

⚠ 제품 출시일 자료는 우리에게 없다. 그러나 **같은 모양의 이벤트**는 셋이나 있다:
  ① **실적 발표** — 날짜가 미리 정해지고 기대가 쌓인다
  ② **지수 편입** — 편입이 예고되면 패시브 매수 기대가 붙는다
  ③ **애널리스트 목표가 상향** — 기대가 공개적으로 쌓인 것 자체다
  셋 모두에서 '이벤트 전에 많이 오른 쪽이 이벤트 뒤에 나쁘다' 가 나오면 원리가 있는 것이고,
  하나에서만 나오면 우연이다.

이미 나온 조각 둘 (오늘):
  · 지수 **편입** 후 20~40일 중앙이 -2.7~-8.1% 로 유니버스(-2.6/-4.3%)보다 나빴다.
  · N6 에서 **발표 전 60일 수익이 높을수록** 성적이 나빴다(절삭 -0.03 → -0.27 → -0.46).
  두 조각이 같은 방향을 가리킨다. 여기서 제대로 잰다.

그리고 사용자 요청 둘째 — **N6 이 월 41건은 많다.** 기대감 축으로 조이면 신호가 줄면서
성적이 유지되는지 본다(우리 규율: 신호가 적어도 된다. 안정성이 먼저다).

  ① 실적 발표 — **발표 전** 랠리 크기별 발표 후 60일 성적
  ② 지수 편입 — 편입 전 랠리 크기별 편입 후 성적 (교차 검증)
  ③ 목표가 상향 집중 — 상향이 몰린 뒤
  ④ N6 조이기 — 기대감 축 + 이미 찾은 축을 겹쳐 **월 10건 이하**를 노린다

    python us_hype.py
"""
import glob, sqlite3, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
W = 148
SINCE = "20160101"
t0 = time.time()


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def sec(t):
    print("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


log("us_scan.pkl")
A = pd.read_pickle(BASE / "data/us_scan.pkl")
A = A[((~A.pref.fillna(False)) & (A.rawclose >= 3)).fillna(False)]
A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
A["amt_q"] = A.groupby("date").amt20.rank(pct=True)
UNI = (A.amt_q >= 0.6).fillna(False)
cal = np.array(sorted(A.date.unique()))
DD = {d: i for i, d in enumerate(cal)}
g = A.groupby("ticker", sort=False)
# **이벤트 전날까지의** 수익률 — 이벤트 당일 갭이 섞이면 '기대감' 이 아니라 '반응' 이 된다
A["pre20"] = g.ret20.shift(1)
A["pre60"] = g.ret60.shift(1)
A["prehi"] = g.fromhi.shift(1)
A["prevol"] = g.vm3.shift(1) / g.vm3.transform(lambda s: s.shift(4).rolling(20).mean())
BEN = {h: A[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in (20, 40, 60)}


def dedup(z, h):
    z = z.sort_values("date")
    keep, last = [], {}
    for t, d_, ix in zip(z.ticker.values, z.date.values, z.index):
        i = DD[d_]
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h
        keep.append(ix)
    return z.loc[keep]


def run(tag, cond, h=60, minn=100, quiet=False):
    z = A[cond.fillna(False)].dropna(subset=[f"n{h}"])
    z = z[(z.buy > 0) & (z.date >= SINCE)]
    Y = dedup(z, h)
    if len(Y) < minn:
        if not quiet:
            print("  %-40s%7s (부족)" % (tag, f"{len(Y):,}"))
        return None
    v = Y[f"n{h}"].astype(float)
    ex = (v - Y.date.map(BEN[h])).mean()
    trim = v[v <= v.quantile(0.95)].mean()
    t5 = v.nlargest(max(1, len(v) // 20)).sum() / v.sum() * 100 if v.sum() != 0 else np.nan
    yr = Y.assign(y=Y.date.str[:4]).groupby("y")[f"n{h}"].median()
    mon = len(set(A[A.date >= SINCE].date.str[:6]))
    if not quiet:
        print("  %-40s%7s%6.1f%8.2f%8.2f%7.0f%%%8.2f%8.2f%7.0f%%%7d/%d"
              % (tag, f"{len(Y):,}", len(Y) / mon, v.mean(), v.median(), (v > 0).mean() * 100,
                 trim, ex, t5, int((yr > 0).sum()), len(yr)))
    return dict(tag=tag, n=len(Y), per=len(Y) / mon, mean=v.mean(), med=v.median(),
                trim=trim, ex=ex, t5=t5, pos=int((yr > 0).sum()), ny=len(yr),
                y26=yr.get("2026", np.nan))


HDR = ("  %-40s%7s%6s%8s%8s%7s%8s%8s%8s%9s" %
       ("조건", "n", "월", "평균", "중앙", "승률", "절삭", "초과", "상위5%", "양수해"))

# ── 실적 이벤트 ──────────────────────────────────────────────────────────
fs = sorted(glob.glob(str(BASE / "data/us/analyst/earn_*.pkl")))
E = pd.concat([pd.read_pickle(f) for f in fs], ignore_index=True)
E["dt"] = pd.to_datetime(E["Earnings Date"], utc=True, errors="coerce")
E = E.dropna(subset=["dt", "Surprise(%)"]).copy()
E["edate"] = E.dt.dt.tz_convert("US/Eastern").dt.strftime("%Y%m%d")
E = E.drop_duplicates(["ticker", "edate"], keep="last")
E["sur"] = E["Surprise(%)"].astype(float)
sz = E.groupby("edate").sur.transform("size")
E["q"] = E.groupby("edate").sur.rank(pct=True)
E = E[sz >= 5].copy()
E["bdate"] = [cal[i] if i < len(cal) else None
              for i in np.searchsorted(cal, E.edate.values, "right")]
E = E.dropna(subset=["bdate"])
A["_k"] = A.ticker + A.date
A["peadq"] = A._k.map(dict(zip(E.ticker + E.bdate, E.q)))
A["gap"] = (A.close / g.close.shift(1) - 1) * 100
HAS = A.peadq.notna()
log("  실적 이벤트 %s행" % f"{int(HAS.sum()):,}")

sec("① 실적 발표 — **발표 전** 랠리가 클수록 발표 후가 나쁜가 (전 발표 · 60일)")
print(HDR)
for lo, hi, lbl in [(-999, -20, "발표 전 60일 -20% 이하 (빠져 있던)"),
                    (-20, -5, "-20 ~ -5%"), (-5, 5, "-5 ~ +5% (조용)"),
                    (5, 20, "+5 ~ +20%"), (20, 50, "+20 ~ +50%"),
                    (50, 999, "**+50% 이상 (기대감 랠리)**")]:
    run("%s" % lbl, UNI & HAS & (A.pre60 > lo) & (A.pre60 <= hi))
print("\n  [20일 기준]")
for lo, hi, lbl in [(-999, -10, "발표 전 20일 -10% 이하"), (-10, 0, "-10 ~ 0%"),
                    (0, 10, "0 ~ +10%"), (10, 25, "+10 ~ +25%"), (25, 999, "**+25% 이상**")]:
    run("%s" % lbl, UNI & HAS & (A.pre20 > lo) & (A.pre20 <= hi))

# ── 지수 편입 (교차 검증) ────────────────────────────────────────────────
sec("② 지수 편입 — 같은 가설을 다른 이벤트에서 (국내 자료 · 교차 검증)")
try:
    KP = pd.read_pickle(BASE / "data/vp_kr.pkl")
    KP = KP.sort_values(["ticker", "date"]).reset_index(drop=True)
    gk = KP.groupby("ticker", sort=False)
    KP["pre60"] = gk.ret60.shift(1)
    kuni = ((~KP.pref) & (KP.close >= 1000) & (KP.amt20.fillna(0) >= 10)
            & (~KP.dil.fillna(False))).fillna(False)
    kcal = np.array(sorted(KP.date.unique()))
    KDD = {d: i for i, d in enumerate(kcal)}
    con = sqlite3.connect(BASE / "data/index_members.db")
    M = pd.read_sql("SELECT idx,date,ticker FROM members", con)
    M["ticker"] = M.ticker.astype(str).str.zfill(6)
    EV = []
    for ix, gg in M.groupby("idx"):
        ds = sorted(gg.date.unique())
        mem = {d: set(gg[gg.date == d].ticker) for d in ds}
        for a_, b_ in zip(ds, ds[1:]):
            i = np.searchsorted(kcal, b_, "left")
            if i >= len(kcal):
                continue
            d0 = kcal[i]
            for t in mem[b_] - mem[a_]:
                EV.append((t, d0))
    KEY = set(t + d for t, d in EV)
    KP["_k"] = KP.ticker + KP.date
    KIN = KP._k.isin(KEY)
    kben = KP[kuni].dropna(subset=["n40"]).groupby("date").n40.mean()
    print("  %-40s%7s%8s%8s%7s%8s" % ("편입 전 60일 수익", "n", "평균", "중앙", "승률", "초과"))
    for lo, hi, lbl in [(-999, 0, "0% 이하 (안 올랐던)"), (0, 20, "0~+20%"),
                        (20, 50, "+20~+50%"), (50, 999, "**+50% 이상 (기대감 랠리)**")]:
        z = KP[(kuni & KIN & (KP.pre60 > lo) & (KP.pre60 <= hi)).fillna(False)]
        z = z.dropna(subset=["n40"])
        z = z[(z.buy > 0) & (z.date >= "20180201")].sort_values("date")
        keep, last = [], {}
        for t, d_, ix in zip(z.ticker.values, z.date.values, z.index):
            i = KDD[d_]
            if last.get(t, -10 ** 9) >= i:
                continue
            last[t] = i + 40
            keep.append(ix)
        Y = z.loc[keep]
        if len(Y) < 30:
            print("  %-40s%7s (부족)" % (lbl, f"{len(Y):,}"))
            continue
        v = Y.n40.astype(float)
        print("  %-40s%7s%8.2f%8.2f%7.0f%%%8.2f"
              % (lbl, f"{len(Y):,}", v.mean(), v.median(), (v > 0).mean() * 100,
                 (v - Y.date.map(kben)).mean()))
    del KP
except Exception as e:
    print("  건너뜀: %r" % e)

# ── N6 조이기 ────────────────────────────────────────────────────────────
CORE = (UNI & HAS & (A.peadq >= 0.7) & (A.gap >= 3)).fillna(False)
sec("③ N6 조이기 — 기대감 축으로 (지금 월 41건이 많다)")
print(HDR)
BASE_R = run("지금 (상위30% & 갭+3%)", CORE)
print("\n  [발표 전 랠리가 작았던 것만]")
for hi in (50, 30, 20, 10, 0):
    run("+ 발표 전 60일 %+d%% 이하" % hi, CORE & (A.pre60 <= hi))
print("\n  [발표 전 20일]")
for hi in (20, 10, 0):
    run("+ 발표 전 20일 %+d%% 이하" % hi, CORE & (A.pre20 <= hi))

sec("④ 겹치기 — 월 10건 이하를 노린다")
print(HDR)
COMB = [
    ("+ 60일↓30% & 거래대금 상위19%", CORE & (A.pre60 <= 30) & (A.amt_q >= 0.81)),
    ("+ 60일↓20% & 거래대금 상위19%", CORE & (A.pre60 <= 20) & (A.amt_q >= 0.81)),
    ("+ 60일↓20% & 고점대비 -15%↑", CORE & (A.pre60 <= 20) & (A.prehi >= -15)),
    ("+ 60일↓20% & 시총 20억$↑", CORE & (A.pre60 <= 20) & (A.marcap >= 2e9)),
    ("+ 60일↓10% & 거래대금 상위19%", CORE & (A.pre60 <= 10) & (A.amt_q >= 0.81)),
    ("+ 60일↓0% & 거래대금 상위19%", CORE & (A.pre60 <= 0) & (A.amt_q >= 0.81)),
    ("+ 60일↓20% & 상위19% & 고점-15%↑", CORE & (A.pre60 <= 20) & (A.amt_q >= 0.81) & (A.prehi >= -15)),
    ("+ 서프라이즈 상위10% & 60일↓20%", UNI & HAS & (A.peadq >= 0.9) & (A.gap >= 3) & (A.pre60 <= 20)),
]
hits = []
for lbl, c in COMB:
    r = run(lbl, c, minn=150)
    if r:
        hits.append(r)

print("\n" + "=" * W)
if BASE_R:
    print("지금: 월 %.1f건 · 중앙 %+.2f%% · 절삭 %+.2f%% · 초과 %+.2f%%p · 상위5% %.0f%% · 양수해 %d/%d"
          % (BASE_R["per"], BASE_R["med"], BASE_R["trim"], BASE_R["ex"], BASE_R["t5"],
             BASE_R["pos"], BASE_R["ny"]))
    print("\n  월 15건 이하이면서 지금보다 절삭·중앙이 나쁘지 않은 칸:")
    for r in hits:
        if r["per"] <= 15 and r["trim"] >= BASE_R["trim"] and r["med"] >= BASE_R["med"]:
            print("  ★ %-40s 월 %.1f건 · 중앙 %+.2f · 절삭 %+.2f · 초과 %+.2f · 2026 %+.2f"
                  % (r["tag"], r["per"], r["med"], r["trim"], r["ex"], r["y26"]))
print("\n총 %.0f초" % (time.time() - t0))
