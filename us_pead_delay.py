# -*- coding: utf-8 -*-
"""**PEAD 진입 지연 민감도 — 운영 방식을 정하려면 이걸 먼저 알아야 한다** (2026-09-15).

채택 후보는 '발표 다음날 시가 매수' 다. 그런데 실적 자료는 yfinance 로 **종목당** 받아야 해서
6,085종목에 약 165분이 걸린다. 매일 돌릴 수 없다.

  · 매일 증분 수집을 새로 만들면(발표 예정일 캐시 → 어제 발표분만 확인) 하루 안에 잡을 수 있지만
    손이 많이 가고 고장 날 곳이 는다.
  · **주 1회 전체 갱신**이면 신호가 최대 7일 늦는다. 그 대가가 얼마인가 — 그걸 모르면 못 정한다.

그래서 **진입을 D+1 ~ D+10 으로 밀어 가며** 성적을 잰다. 둔감하면 주 1회로 충분하고,
민감하면 증분 수집을 만들어야 한다.

⚠ 지연은 '늦게 사는 것' 이지 '늦게 아는 것' 이 아니다 — 조건(서프라이즈·갭)은 발표 다음날
   기준 그대로 두고 **매수만 미룬다**. 실제 운영과 같은 모양이다.

    python us_pead_delay.py
"""
import glob, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
W = 120
SINCE = "20160101"
HOLD = 60
t0 = time.time()


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)


fs = sorted(glob.glob(str(BASE / "data/us/analyst/*.pkl")))
E = pd.concat([pd.read_pickle(f) for f in fs], ignore_index=True)
E["dt"] = pd.to_datetime(E["Earnings Date"], utc=True, errors="coerce")
E = E.dropna(subset=["dt", "Surprise(%)"]).copy()
E["edate"] = E.dt.dt.tz_convert("US/Eastern").dt.strftime("%Y%m%d")
E = E.drop_duplicates(["ticker", "edate"], keep="last")

log("us_scan.pkl")
A = pd.read_pickle(BASE / "data/us_scan.pkl")
A = A[((~A.pref.fillna(False)) & (A.rawclose >= 3)).fillna(False)]
A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
A["amt_q"] = A.groupby("date").amt20.rank(pct=True)
UNI = (A.amt_q >= 0.6).fillna(False)
cal = np.array(sorted(A.date.unique()))
DD = {d: i for i, d in enumerate(cal)}
E["bdate"] = [cal[i] if i < len(cal) else None
              for i in np.searchsorted(cal, E.edate.values, "right")]
E = E.dropna(subset=["bdate"])
E["sur"] = E["Surprise(%)"].astype(float)
E["q"] = E.groupby("bdate").sur.rank(pct=True)
E["n_day"] = E.groupby("bdate").sur.transform("size")
E = E[E.n_day >= 5]
A["_k"] = A.ticker + A.date
A["peadq"] = A._k.map(dict(zip(E.ticker + E.bdate, E.q)))
g = A.groupby("ticker", sort=False)
A["ret1"] = (A.close / g.close.shift(1) - 1) * 100
A["row"] = np.arange(len(A))

# 조건은 '발표 다음날(D+1)' 기준 그대로 — 여기가 신호일이다
SIG = (UNI & A.peadq.notna() & (A.peadq >= 0.7) & (A.ret1 >= 3)).fillna(False)
Z = A[SIG].copy()
Z = Z[(Z.buy > 0) & (Z.date >= SINCE)].sort_values("date")
keep, last = [], {}
for t, d_, ix in zip(Z.ticker.values, Z.date.values, Z.index):
    i = DD[d_]
    if last.get(t, -10 ** 9) >= i:
        continue
    last[t] = i + HOLD
    keep.append(ix)
Z = Z.loc[keep].copy()
log("신호 %s건" % f"{len(Z):,}")

# 지연 매수: D+k 행의 buy(=그 다음날 시가)로 사고, 원래 청산일(D+1+HOLD)에 판다.
# 즉 **늦게 사면 보유기간이 그만큼 짧아진다** — 실제 운영과 같다(청산은 규칙이 정한 날).
BUYV = A.buy.values
CLOSEV = A.close.values
COSTV = A.cost.values
TICK = A.ticker.values
ROW = Z.row.values
BEN = {}
for k in range(0, 11):
    # 같은 종목인지 확인하며 k행 뒤로 민다
    idx = np.minimum(ROW + k, len(A) - 1)
    same = TICK[idx] == TICK[ROW]
    idx = np.where(same, idx, ROW)
    BEN[k] = idx

EXIT = np.minimum(ROW + HOLD, len(A) - 1)
same_exit = TICK[EXIT] == TICK[ROW]

print("\n" + "=" * W)
print("진입 지연 민감도 — 조건은 발표 다음날 그대로, **매수만** D+1…D+11 로 민다")
print("청산일은 그대로(신호일 +60거래일) — 늦게 사면 보유기간이 짧아진다. 실제 운영과 같다.")
print("=" * W)
print("  %-14s%8s%9s%9s%8s%9s%9s%9s" % ("매수 시점", "n", "평균%", "중앙%", "승률", "절삭%", "2026", "양수해"))
res = []
for k in range(0, 11):
    bi = BEN[k]
    px_buy = BUYV[bi]
    px_sell = CLOSEV[EXIT]
    ok = same_exit & (TICK[bi] == TICK[ROW]) & np.isfinite(px_buy) & np.isfinite(px_sell) & (px_buy > 0)
    r = np.where(ok, (px_sell / px_buy - 1) * 100 - COSTV[ROW], np.nan)
    v = pd.Series(r).dropna()
    if len(v) < 100:
        continue
    d = Z.iloc[: len(r)].copy()
    d["r"] = r
    d = d.dropna(subset=["r"])
    trim = v[v <= v.quantile(0.95)].mean()
    yr = d.assign(y=d.date.str[:4]).groupby("y").r.median()
    lbl = "D+%d (발표+%d)" % (k + 1, k + 1)
    print("  %-14s%8s%+9.2f%+9.2f%7.0f%%%+9.2f%+9.2f%7d/%d"
          % (lbl, f"{len(v):,}", v.mean(), v.median(), (v > 0).mean() * 100, trim,
             yr.get("2026", np.nan), int((yr > 0).sum()), len(yr)))
    res.append((k + 1, v.mean(), v.median(), trim))

R = pd.DataFrame(res, columns=["d", "mean", "med", "trim"])
print("\n  D+1 대비 남는 비율")
print("  %-14s%10s%10s%10s" % ("매수 시점", "평균", "중앙", "절삭"))
b = R.iloc[0]
for _, r in R.iterrows():
    print("  %-14s%9.0f%%%9.0f%%%9s"
          % ("D+%d" % r["d"], r["mean"] / b["mean"] * 100, r["med"] / b["med"] * 100,
             "%.0f%%" % (r["trim"] / b["trim"] * 100) if b["trim"] > 0 else "—"))
print("\n  ※ 주 1회 갱신이면 평균 **D+3~4**, 최악 D+6 쯤이 된다(주말 포함).")
print("    그 구간에서 성적이 크게 안 깎이면 주 1회로 충분하다.")
print("\n총 %.0f초" % (time.time() - t0))
