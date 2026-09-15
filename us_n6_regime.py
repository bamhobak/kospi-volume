# -*- coding: utf-8 -*-
"""**[실적 서프라이즈]는 국면을 타나?** (2026-09-16 물음).

사이트 정의상 N6 는 `regime:'both' · gate:'always'` — 국면 조건이 없다.
그런데 "없다" 는 건 **안 걸었다**는 뜻이지 **국면을 안 탄다**는 뜻이 아니다.
[잔잔한 급등주]처럼 게이트를 안 걸어도 신호가 한쪽에만 몰리는 경우가 있다(내생적 게이트).

그래서 둘을 나눠 본다.
  ① **신호가 어디서 나오나** — 상승 국면 / 하락 국면 각각 몇 건
  ② **성적이 다른가** — 국면별 평균·중앙·승률·절삭
  ③ 국면 게이트를 걸면 나아지나 — 상승 전용 / 하락 전용
  ④ 견줄 상대 — 나머지 5규칙도 같은 표로

국면 정의는 사이트와 같다: **S&P500 종가가 60일 이동평균 위면 상승, 아래면 하락.**

    python us_n6_regime.py
"""
import glob, pickle, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
W = 108
SINCE = "20160101"
NM = {"N1": "상승장 신고가", "N2": "낙폭과대", "N3": "저PBR 낙폭", "N4": "자사주 낙폭",
      "N5": "잔잔한 급등주", "N6": "실적 서프라이즈"}
GATE = {"N1": "상승 전용", "N2": "하락 전용", "N3": "하락 전용",
        "N4": "없음", "N5": "없음", "N6": "없음"}
t0 = time.time()


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def sec(t):
    print("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


# ── S&P500 60일선으로 국면을 만든다 (사이트와 같은 정의) ──────────────────
log("국면 만드는 중 — S&P500 60일선")
SPX = None
for f in ["data/us/spx.pkl", "data/us/index.pkl", "data/us_index.pkl"]:
    p = BASE / f
    if p.exists():
        SPX = pd.read_pickle(p)
        log("  %s 에서 읽음" % f)
        break
if SPX is None:
    # 패널에서 시총 가중 지수를 만들어 대신 쓴다
    A = pd.read_pickle(BASE / "data/us_scan.pkl")
    g = A.groupby("date").apply(lambda z: np.average(z.ret1d.fillna(0), weights=z.marcap.fillna(0))
                                if z.marcap.notna().any() else 0.0)
    SPX = pd.DataFrame({"date": g.index, "close": (1 + g.values / 100).cumprod()})
    log("  지수 파일이 없어 시총가중 지수를 만들어 씀")
SPX = SPX.sort_values("date").reset_index(drop=True)
SPX["ma60"] = SPX.close.rolling(60).mean()
SPX["up"] = SPX.close > SPX.ma60
UP = dict(zip(SPX.date, SPX.up))

# ── N6 신호 (사이트 정의 그대로) ─────────────────────────────────────────
E = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(str(BASE / "data/us/analyst/*.pkl")))],
              ignore_index=True)
E["dt"] = pd.to_datetime(E["Earnings Date"], utc=True, errors="coerce")
E = E.dropna(subset=["dt", "Surprise(%)"]).copy()
E["edate"] = E.dt.dt.tz_convert("US/Eastern").dt.strftime("%Y%m%d")
E = E.drop_duplicates(["ticker", "edate"], keep="last")
A = pd.read_pickle(BASE / "data/us_scan.pkl")
A = A[((~A.pref.fillna(False)) & (A.rawclose >= 3)).fillna(False)]
A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
A["amt_q"] = A.groupby("date").amt20.rank(pct=True)
cal = np.array(sorted(A.date.unique()))
DD = {d: i for i, d in enumerate(cal)}
E["bdate"] = [cal[i] if i < len(cal) else None
              for i in np.searchsorted(cal, E.edate.values, "right")]
E = E.dropna(subset=["bdate"])
E["sur"] = E["Surprise(%)"].astype(float)
E["q"] = E.groupby("bdate").sur.rank(pct=True)
E = E[E.groupby("bdate").sur.transform("size") >= 5]
A["_k"] = A.ticker + A.date
A["peadq"] = A._k.map(dict(zip(E.ticker + E.bdate, E.q)))
A["ret1"] = (A.close / A.groupby("ticker", sort=False).close.shift(1) - 1) * 100
X = A[((A.amt_q >= 0.6) & (A.peadq >= 0.7) & (A.ret1 >= 3)).fillna(False)].dropna(subset=["n60"])
X = X[(X.buy > 0) & (X.date >= SINCE)].sort_values("date")
keep, last = [], {}
for t, d_, ix in zip(X.ticker.values, X.date.values, X.index):
    i = DD[d_]
    if last.get(t, -10 ** 9) >= i:
        continue
    last[t] = i + 60
    keep.append(ix)
Y = X.loc[keep]
N6 = pd.DataFrame({"date": Y.date.values, "ticker": Y.ticker.values, "rid": "N6",
                   "ret": Y.n60.astype(float).values})
del A, X, Y

with open(BASE / "data" / "sector_drop_us_sig.pkl", "rb") as f:
    C = pickle.load(f)
S5, DS = C["S"], C["DS"]
N6 = N6[N6.date.isin(set(DS))].reset_index(drop=True)
ALL = pd.concat([S5[["date", "ticker", "rid", "ret"]], N6], ignore_index=True)
ALL["up"] = ALL.date.map(UP)
ALL = ALL.dropna(subset=["up"])
ALL["up"] = ALL.up.astype(bool)

nup = sum(1 for d in DS if UP.get(d) is True)
ndn = sum(1 for d in DS if UP.get(d) is False)
log("  거래일 %s일 — 상승 국면 %.0f%% · 하락 국면 %.0f%%"
    % (f"{nup + ndn:,}", nup / (nup + ndn) * 100, ndn / (nup + ndn) * 100))

sec("① 신호가 어디서 나오나 — 게이트를 안 걸었을 때")
print("  (거래일 자체는 상승 %.0f%% · 하락 %.0f%% 다. 이 비율보다 치우치면 국면을 타는 것)"
      % (nup / (nup + ndn) * 100, ndn / (nup + ndn) * 100))
print("\n  %-16s%10s%10s%10s%12s" % ("규칙", "게이트", "신호", "상승 국면", "하락 국면"))
for r in ["N1", "N2", "N3", "N4", "N5", "N6"]:
    z = ALL[ALL.rid == r]
    if not len(z):
        continue
    print("  %-16s%10s%10s%9.0f%%%11.0f%%"
          % (NM[r], GATE[r], f"{len(z):,}", z.up.mean() * 100, (~z.up).mean() * 100))
print("\n  ※ [상승장 신고가]·[낙폭과대]·[저PBR 낙폭]이 100%/0% 인 건 게이트를 걸었기 때문이다.")

sec("② 국면별 성적 — 게이트 없는 세 규칙")
print("  %-16s%12s%9s%9s%8s%9s" % ("규칙", "국면", "신호", "중앙%", "승률", "절삭평균"))
for r in ["N4", "N5", "N6"]:
    for lbl, m in (("상승 국면", True), ("하락 국면", False)):
        v = ALL[(ALL.rid == r) & (ALL.up == m)].ret.astype(float)
        if len(v) < 20:
            print("  %-16s%12s%9s%9s%8s%9s" % (NM[r] if m else "", lbl, f"{len(v):,}", "—", "—", "—"))
            continue
        tr = v[v <= v.quantile(0.95)].mean()
        print("  %-16s%12s%9s%+9.2f%7.0f%%%+9.2f"
              % (NM[r] if m else "", lbl, f"{len(v):,}", v.median(), (v > 0).mean() * 100, tr))
    print()

sec("③ 그럼 [실적 서프라이즈]에 국면 게이트를 걸면 나아지나")
v = ALL[ALL.rid == "N6"].ret.astype(float)
print("  %-20s%9s%9s%9s%8s%9s%11s"
      % ("구성", "신호", "평균%", "중앙%", "승률", "절삭평균", "상위5%기여"))
for lbl, m in (("게이트 없음 (지금)", None), ("상승 전용", True), ("하락 전용", False)):
    z = ALL[ALL.rid == "N6"] if m is None else ALL[(ALL.rid == "N6") & (ALL.up == m)]
    v = z.ret.astype(float)
    tr = v[v <= v.quantile(0.95)].mean()
    t5 = v.nlargest(max(1, len(v) // 20)).sum() / v.sum() * 100
    print("  %-20s%9s%+9.2f%+9.2f%7.0f%%%+9.2f%10.0f%%"
          % (lbl, f"{len(v):,}", v.mean(), v.median(), (v > 0).mean() * 100, tr, t5))

sec("④ 연도별 — 국면을 나눠도 양쪽 다 살아 있나")
z = ALL[ALL.rid == "N6"].copy()
z["y"] = z.date.str[:4]
print("  %-12s" % "국면" + "".join("%10s" % y for y in range(2016, 2027)))
for lbl, m in (("상승 국면", True), ("하락 국면", False)):
    row = ""
    for y in range(2016, 2027):
        g = z[(z.y == str(y)) & (z.up == m)].ret.astype(float)
        row += ("%9.1f%%" % g.median()) if len(g) >= 10 else ("%10s" % ("(%d)" % len(g)))
    print("  %-12s%s" % (lbl, row))
print("\n  ※ 괄호는 표본이 10건 미만이라 못 재는 칸이다.")
print("\n총 %.0f초" % (time.time() - t0))
