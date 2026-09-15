# -*- coding: utf-8 -*-
"""**시총 축 — 큰 것만? 작은 것만?** 미장 6규칙 전부 (2026-09-15 요청).

물음: "시총을 높은 것만 사기 / 낮은 것만 사기, 어떤 것도 조율할 게 없어?"

지금까지 조각으로만 봤다.
  · [실적 서프라이즈] 시총 20억$↑ → 절삭 +1.03(좋음) 인데 **계좌는 50/100 동전**
  · 내부자 매수 → 같은 달 시총 순위로 재니 **단조가 아예 없었다**
    (절대 문턱으로 본 '클수록 나쁨' 은 시대별 물가가 만든 착시였다)
  · [상승장 신고가] → 예전 us_n1_* 에서 '시총 조이기는 계좌에서 손해' 로 이미 기각
여기서는 **6규칙 전부를 십분위로** 훑어 단조성이 있는지 한 번에 본다. 양방향 다.

⚠ **절대 문턱(20억$ 같은)을 쓰면 안 된다.** 2016년 20억 달러와 2026년 20억 달러는 다른
   규모다. **같은 달 안에서의 시총 순위**로 재야 시대 효과가 지워진다.

판정: 십분위 상관 r 이 뚜렷해야 축이 있는 것이다. 0 근처면 조율할 게 없다.

    python us_cap_axis.py
"""
import glob, pickle, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
W = 124
SINCE = "20160101"
NM = {"N1": "상승장 신고가", "N2": "낙폭과대", "N3": "저PBR 낙폭",
      "N4": "자사주 낙폭", "N5": "잔잔한 급등주", "N6": "실적 서프라이즈"}
t0 = time.time()


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def sec(t):
    print("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


log("us_scan.pkl — 시총을 붙이려고")
A = pd.read_pickle(BASE / "data/us_scan.pkl")
A = A[["ticker", "date", "marcap"]].dropna(subset=["marcap"])
A["_k"] = A.ticker + A.date
# **같은 달 안에서의 시총 순위** — 시대별 물가를 지운다
A["mq"] = A.groupby(A.date.str[:6]).marcap.rank(pct=True)
MQ = dict(zip(A._k, A.mq))
MC = dict(zip(A._k, A.marcap))
del A
log("  시총 순위 %s행" % f"{len(MQ):,}")

with open(BASE / "data" / "sector_drop_us_sig.pkl", "rb") as f:
    C = pickle.load(f)
S, DS, ADI, PCT = C["S"], C["DS"], C["ADI"], C["PCT"]
S = S.copy()
S["mq"] = (S.ticker + S.date).map(MQ)
S["mc"] = (S.ticker + S.date).map(MC)

# N6(실적 서프라이즈)은 캐시에 없다 — 만들어 붙인다
E = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(str(BASE / "data/us/analyst/earn_*.pkl")))],
              ignore_index=True)
E["dt"] = pd.to_datetime(E["Earnings Date"], utc=True, errors="coerce")
E = E.dropna(subset=["dt", "Surprise(%)"]).copy()
E["edate"] = E.dt.dt.tz_convert("US/Eastern").dt.strftime("%Y%m%d")
E = E.drop_duplicates(["ticker", "edate"], keep="last")
E["sur"] = E["Surprise(%)"].astype(float)
B = pd.read_pickle(BASE / "data/us_scan.pkl")
B = B[((~B.pref.fillna(False)) & (B.rawclose >= 3)).fillna(False)]
B = B.sort_values(["ticker", "date"]).reset_index(drop=True)
B["amt_q"] = B.groupby("date").amt20.rank(pct=True)
cal = np.array(sorted(B.date.unique()))
DD = {d: i for i, d in enumerate(cal)}
sz = E.groupby("edate").sur.transform("size")
E["q"] = E.groupby("edate").sur.rank(pct=True)
E = E[sz >= 5].copy()
E["bdate"] = [cal[i] if i < len(cal) else None
              for i in np.searchsorted(cal, E.edate.values, "right")]
E = E.dropna(subset=["bdate"])
B["_k"] = B.ticker + B.date
B["peadq"] = B._k.map(dict(zip(E.ticker + E.bdate, E.q)))
B["gap"] = (B.close / B.groupby("ticker", sort=False).close.shift(1) - 1) * 100
c6 = ((B.amt_q >= 0.6) & B.peadq.notna() & (B.peadq >= 0.7) & (B.gap >= 3)).fillna(False)
z = B[c6].dropna(subset=["n60"])
z = z[(z.buy > 0) & (z.date >= SINCE)].sort_values("date")
keep, last = [], {}
for t, d_, ix in zip(z.ticker.values, z.date.values, z.index):
    i = DD[d_]
    if last.get(t, -10 ** 9) >= i:
        continue
    last[t] = i + 60
    keep.append(ix)
Y = z.loc[keep]
N6 = pd.DataFrame({"date": Y.date.values, "ticker": Y.ticker.values, "rid": "N6",
                   "ret": Y.n60.astype(float).values, "amt20": Y.amt20.values,
                   "hold": 60, "pct": 5, "mx": 3})
N6["di"] = [ADI.get(d, -1) for d in N6.date.values]
N6 = N6[N6.di >= 0]
N6["mq"] = (N6.ticker + N6.date).map(MQ)
N6["mc"] = (N6.ticker + N6.date).map(MC)
del B
ALL = pd.concat([S, N6], ignore_index=True)
log("  신호 %s건 (N6 %s건 포함)" % (f"{len(ALL):,}", f"{len(N6):,}"))

sec("① 규칙별 시총 십분위 — 1분위=작은 쪽 · 10분위=큰 쪽 (같은 달 안 순위)")
print("  %-16s%6s" % ("규칙", "분위") + "".join("%8d" % i for i in range(1, 11)) + "%9s%9s"
      % ("상관r", "판정"))
RES = {}
for r in ["N1", "N2", "N3", "N4", "N5", "N6"]:
    z = ALL[(ALL.rid == r) & ALL.mq.notna()]
    if len(z) < 300:
        continue
    med, trim, n = [], [], []
    for i in range(10):
        lo, hi = i / 10, (i + 1) / 10 + (0.001 if i == 9 else 0)
        g = z[(z.mq > lo) & (z.mq <= hi)]
        n.append(len(g))
        if len(g) < 20:
            med.append(np.nan); trim.append(np.nan); continue
        v = g.ret.astype(float)
        med.append(v.median())
        trim.append(v[v <= v.quantile(0.95)].mean())
    m = np.array(med, float)
    ok = ~np.isnan(m)
    rr = np.corrcoef(np.arange(1, 11)[ok], m[ok])[0, 1] if ok.sum() >= 6 else np.nan
    RES[r] = (m, np.array(trim, float), rr)
    verdict = "큰 쪽" if rr > 0.4 else ("작은 쪽" if rr < -0.4 else "없음")
    print("  %-16s%6s" % (NM[r], "중앙")
          + "".join(("%8.1f" % x) if x == x else "%8s" % "—" for x in med)
          + "%9.2f%9s" % (rr, verdict))
    print("  %-16s%6s" % ("", "절삭")
          + "".join(("%8.1f" % x) if x == x else "%8s" % "—" for x in trim))
    print("  %-16s%6s" % ("", "건수")
          + "".join("%8s" % f"{x:,}" for x in n))
    print()
print("  ※ 상관 r 이 +0.4 넘으면 '큰 쪽이 낫다', -0.4 밑이면 '작은 쪽이 낫다'.")
print("    0 근처면 시총으로는 조율할 게 없다는 뜻이다.")

sec("② 상·하위 30%만 샀을 때 — 규칙 단위")
print("  %-16s%10s%9s%9s%8s%9s   |%9s%9s%8s%9s" %
      ("규칙", "전체 중앙", "절삭", "n", "", "", "큰쪽 중앙", "절삭", "작은쪽", "절삭"))
for r in ["N1", "N2", "N3", "N4", "N5", "N6"]:
    z = ALL[(ALL.rid == r) & ALL.mq.notna()]
    if len(z) < 300:
        continue
    v = z.ret.astype(float)
    hi = z[z.mq >= 0.7].ret.astype(float)
    lo = z[z.mq <= 0.3].ret.astype(float)
    tr = lambda x: x[x <= x.quantile(0.95)].mean() if len(x) > 20 else np.nan
    print("  %-16s%9.2f%%%9.2f%9s%8s%9s   |%8.2f%%%9.2f%8.2f%%%9.2f"
          % (NM[r], v.median(), tr(v), f"{len(z):,}", "", "",
             hi.median(), tr(hi), lo.median(), tr(lo)))
print("\n총 %.0f초" % (time.time() - t0))
