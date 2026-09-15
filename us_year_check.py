# -*- coding: utf-8 -*-
"""**2026 수치가 공정한가 + 시총 구간별** (2026-09-15 요청).

의심: "내부자 2026 만 음수인 게 이상한데, 제대로 체크한 거 맞나."

⚠ 의심이 맞을 이유가 하나 있다 — **2026은 반쪽 해다.**
   오늘이 2026-09-15 인데 내부자 규칙은 **40거래일 보유**다. 그러면 2026-07 중순 이후 신호는
   40일 뒤가 아직 없어 `n40` 이 결측이고 표본에서 통째로 빠진다. PEAD 는 **60일**이라 더 심해서
   2026-06 이후가 빠진다. 즉 2026 은 **1~7월(또는 1~6월)만** 담긴 값이고, 12개월인 다른 해와
   나란히 놓으면 안 된다.

  ① 연도별 **표본이 실제로 몇 월까지 담겼나**
  ② 같은 잣대로 — 모든 해를 **1~6월 신호만** 잘라 다시 비교
  ③ 2026 의 음수가 특정 달에 몰렸나
  ④ **시총 십분위별** 성적 (내부자·PEAD 둘 다)

    python us_year_check.py
"""
import glob, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
W = 128
SINCE = "20160101"
t0 = time.time()


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def sec(t):
    print("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


def dedup(z, h, DD):
    z = z.sort_values("date")
    keep, last = [], {}
    for t, d_, ix in zip(z.ticker.values, z.date.values, z.index):
        i = DD[d_]
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h
        keep.append(ix)
    return z.loc[keep]


# ══════════════════════════════════════════════════════════════════════════
log("us_ins.pkl (내부자)")
K = pd.read_pickle(BASE / "data/us_ins.pkl")
K = K[["ticker", "date", "amt20", "buy", "pref", "rawclose", "n40", "bv", "marcap", "fromhi"]].copy()
K = K[((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
K["amt_q"] = K.groupby("date").amt20.rank(pct=True)
udK = sorted(K.date.unique())
DDK = {d: i for i, d in enumerate(udK)}
zi = K[((K.amt_q >= 0.6) & (K.bv >= 1e6)).fillna(False)]
RAW = zi[(zi.buy > 0) & (zi.date >= SINCE)].copy()       # 결측 포함 (수익률 없는 것까지)
IN_ALL = dedup(RAW, 40, DDK)
IN = IN_ALL.dropna(subset=["n40"]).copy()
IN["r"] = IN.n40.astype(float)
log("  내부자 신호 %s건 (수익률 있는 것 %s)" % (f"{len(IN_ALL):,}", f"{len(IN):,}"))

sec("① 연도별 표본이 몇 월까지 담겼나 — 내부자(40일 보유)")
print("  %-6s%9s%9s%12s%10s%10s" % ("연도", "신호(전)", "수익률有", "마지막 신호월", "중앙%", "평균%"))
for y, gg in IN_ALL.assign(y=IN_ALL.date.str[:4]).groupby("y"):
    have = gg.dropna(subset=["n40"])
    print("  %-6s%9s%9s%12s%10s%10s"
          % (y, f"{len(gg):,}", f"{len(have):,}",
             have.date.max()[4:6] + "월" if len(have) else "—",
             "%+.2f" % have.n40.median() if len(have) else "—",
             "%+.2f" % have.n40.mean() if len(have) else "—"))
print("  ※ '마지막 신호월' 이 다른 해보다 빠르면 그 해는 **반쪽**이다 — 그대로 견주면 안 된다.")

sec("② 같은 잣대 — 모든 해를 **1~6월 신호만** 잘라 비교 (내부자)")
H1 = IN[IN.date.str[4:6] <= "06"]
print("  %-6s%9s%10s%10s%9s" % ("연도", "신호", "중앙%", "평균%", "승률"))
for y, gg in H1.assign(y=H1.date.str[:4]).groupby("y"):
    print("  %-6s%9s%+10.2f%+10.2f%8.0f%%"
          % (y, f"{len(gg):,}", gg.r.median(), gg.r.mean(), (gg.r > 0).mean() * 100))
h1y = H1.assign(y=H1.date.str[:4]).groupby("y").r.median()
print("  → 1~6월만 보면 양수해 %d/%d" % ((h1y > 0).sum(), len(h1y)))

sec("③ 2026 의 음수가 특정 달에 몰렸나 (내부자)")
z26 = IN[IN.date.str[:4] == "2026"]
print("  %-8s%8s%10s%10s%9s" % ("월", "신호", "중앙%", "평균%", "승률"))
for m, gg in z26.assign(m=z26.date.str[4:6]).groupby("m"):
    print("  %-8s%8s%+10.2f%+10.2f%8.0f%%"
          % (m + "월", f"{len(gg):,}", gg.r.median(), gg.r.mean(), (gg.r > 0).mean() * 100))

sec("④ 시총 십분위별 — 내부자")
IN["mq"] = IN.groupby(IN.date.str[:6]).marcap.rank(pct=True)   # 같은 달 안에서의 시총 순위
print("  %-10s%8s%10s%10s%9s%10s%11s" % ("시총 십분위", "n", "평균%", "중앙%", "승률", "절삭%", "상위5%기여"))
for i in range(10):
    lo, hi = i / 10, (i + 1) / 10 + (0.001 if i == 9 else 0)
    gg = IN[(IN.mq > lo) & (IN.mq <= hi)]
    if len(gg) < 50:
        continue
    v = gg.r
    trim = v[v <= v.quantile(0.95)].mean()
    t5 = v.nlargest(max(1, len(v) // 20)).sum() / v.sum() * 100 if v.sum() != 0 else np.nan
    print("  %-10s%8s%+10.2f%+10.2f%8.0f%%%+10.2f%10.0f%%"
          % ("%d분위" % (i + 1), f"{len(gg):,}", v.mean(), v.median(),
             (v > 0).mean() * 100, trim, t5))
print("  ※ 1분위=시총 작은 쪽 · 10분위=큰 쪽 (같은 달 안에서의 순위)")
del K, zi, RAW

# ══════════════════════════════════════════════════════════════════════════
log("us_scan.pkl (PEAD)")
fs = sorted(glob.glob(str(BASE / "data/us/analyst/*.pkl")))
E = pd.concat([pd.read_pickle(f) for f in fs], ignore_index=True)
E["dt"] = pd.to_datetime(E["Earnings Date"], utc=True, errors="coerce")
E = E.dropna(subset=["dt", "Surprise(%)"]).copy()
E["edate"] = E.dt.dt.tz_convert("US/Eastern").dt.strftime("%Y%m%d")
E = E.drop_duplicates(["ticker", "edate"], keep="last")
A = pd.read_pickle(BASE / "data/us_scan.pkl")
A = A[((~A.pref.fillna(False)) & (A.rawclose >= 3)).fillna(False)]
A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
A["amt_q"] = A.groupby("date").amt20.rank(pct=True)
cal = np.array(sorted(A.date.unique()))
DDA = {d: i for i, d in enumerate(cal)}
E["bdate"] = [cal[i] if i < len(cal) else None
              for i in np.searchsorted(cal, E.edate.values, "right")]
E = E.dropna(subset=["bdate"])
E["sur"] = E["Surprise(%)"].astype(float)
E["q"] = E.groupby("bdate").sur.rank(pct=True)
E["n_day"] = E.groupby("bdate").sur.transform("size")
E = E[E.n_day >= 5]
A["_k"] = A.ticker + A.date
A["peadq"] = A._k.map(dict(zip(E.ticker + E.bdate, E.q)))
A["ret1"] = (A.close / A.groupby("ticker", sort=False).close.shift(1) - 1) * 100
c = (A.peadq.notna() & (A.amt_q >= 0.6) & (A.peadq >= 0.7) & (A.ret1 >= 3)).fillna(False)
zp = A[c]
RAWP = zp[(zp.buy > 0) & (zp.date >= SINCE)].copy()
PE_ALL = dedup(RAWP, 60, DDA)
PE = PE_ALL.dropna(subset=["n60"]).copy()
PE["r"] = PE.n60.astype(float)
log("  PEAD 신호 %s건 (수익률 있는 것 %s)" % (f"{len(PE_ALL):,}", f"{len(PE):,}"))

sec("⑤ 연도별 표본 — PEAD(60일 보유)")
print("  %-6s%9s%9s%12s%10s%10s" % ("연도", "신호(전)", "수익률有", "마지막 신호월", "중앙%", "평균%"))
for y, gg in PE_ALL.assign(y=PE_ALL.date.str[:4]).groupby("y"):
    have = gg.dropna(subset=["n60"])
    print("  %-6s%9s%9s%12s%10s%10s"
          % (y, f"{len(gg):,}", f"{len(have):,}",
             have.date.max()[4:6] + "월" if len(have) else "—",
             "%+.2f" % have.n60.median() if len(have) else "—",
             "%+.2f" % have.n60.mean() if len(have) else "—"))

sec("⑥ 같은 잣대 — 1~6월 신호만 (PEAD)")
H1P = PE[PE.date.str[4:6] <= "06"]
print("  %-6s%9s%10s%10s%9s" % ("연도", "신호", "중앙%", "평균%", "승률"))
for y, gg in H1P.assign(y=H1P.date.str[:4]).groupby("y"):
    print("  %-6s%9s%+10.2f%+10.2f%8.0f%%"
          % (y, f"{len(gg):,}", gg.r.median(), gg.r.mean(), (gg.r > 0).mean() * 100))
h1p = H1P.assign(y=H1P.date.str[:4]).groupby("y").r.median()
print("  → 1~6월만 보면 양수해 %d/%d" % ((h1p > 0).sum(), len(h1p)))

sec("⑦ 시총 십분위별 — PEAD")
PE["mq"] = PE.groupby(PE.date.str[:6]).marcap.rank(pct=True)
print("  %-10s%8s%10s%10s%9s%10s%11s" % ("시총 십분위", "n", "평균%", "중앙%", "승률", "절삭%", "상위5%기여"))
for i in range(10):
    lo, hi = i / 10, (i + 1) / 10 + (0.001 if i == 9 else 0)
    gg = PE[(PE.mq > lo) & (PE.mq <= hi)]
    if len(gg) < 50:
        continue
    v = gg.r
    trim = v[v <= v.quantile(0.95)].mean()
    t5 = v.nlargest(max(1, len(v) // 20)).sum() / v.sum() * 100 if v.sum() != 0 else np.nan
    print("  %-10s%8s%+10.2f%+10.2f%8.0f%%%+10.2f%10.0f%%"
          % ("%d분위" % (i + 1), f"{len(gg):,}", v.mean(), v.median(),
             (v > 0).mean() * 100, trim, t5))
print("\n총 %.0f초" % (time.time() - t0))
