# -*- coding: utf-8 -*-
"""**주봉 눌림목 — 마지막 관문** (week_pullback2.py 후속, 2026-09-16).

조이니 숫자가 크게 좋아졌다. 그런데 **그게 함정의 얼굴**이다.
  시총 하위50% + 상승폭 +30~100% → 평균 **+7.97%** · 초과 +5.12 · 절삭 2.83 (n=229)
  시총 하위50% + PBR ≤ 3        → 평균 **+6.00%** · 초과 +4.34 · 절삭 2.13 (n=342)
152칸을 돌렸으니 이 정도 숫자는 **우연히도 나온다**. 기준선(조건 없음)은 이미
다중검정에서 기각됐다(진짜일확률 81.8%). 조인 칸은 표본이 더 작아 더 위험하다.

그래서 여기서는 **살아남는지만** 본다. 통과 기준은 집안 정본이다.
  ① 다중검정 보정(152칸) — 진짜일확률 95% 이상
  ② **최근 해 성적** — 2026 진입분이 음수면 기각한다([[bull-axis-n1]] 전례)
  ③ 연도별 양수 개수와 학습·검증 분리
  ④ 상위5% 기여 — 복권형인가
  ⑤ 시총 하위50% 가 진짜 축인가 — 십분위로 단조인지 (한 칸만 좋으면 우연이다)

    python week_pullback3.py
"""
import pickle, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path
from vp_lib import Runner
from verdict import deflated_sharpe

BASE = Path(__file__).parent
W = 132
SINCE = "20160101"
NTRIALS = 152            # week_pullback.py 110칸 + week_pullback2.py 42칸
t0 = time.time()


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def sec(t):
    print("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


log("미장 패널 읽는 중")
U = pd.read_pickle(BASE / "data/us_scan.pkl")
U = U[((~U.pref.fillna(False)) & (U.rawclose >= 3)).fillna(False)]
U = U.sort_values(["ticker", "date"]).reset_index(drop=True)
AQ = U.groupby("date").amt20.rank(pct=True)
MQ = U.groupby(U.date.str[:6]).marcap.rank(pct=True)
UNI = (AQ >= 0.60).fillna(False)

dt = pd.to_datetime(U.date, format="%Y%m%d")
Uw = U.assign(_wk=(dt - pd.to_timedelta(dt.dt.dayofweek, unit="D")).dt.strftime("%Y%m%d"))
Wk = (Uw.groupby(["ticker", "_wk"], sort=True)
        .agg(date=("date", "last"), close=("close", "last")).reset_index())
Wk = Wk.sort_values(["ticker", "_wk"]).reset_index(drop=True)
g = Wk.groupby("ticker", sort=False)
wdt = pd.to_datetime(Wk._wk, format="%Y%m%d")
cont = (wdt - wdt.groupby(Wk.ticker).shift(1)).dt.days.eq(7).fillna(False)
wret = (Wk.close / g.close.shift(1) - 1) * 100
up = ((wret > 0) & cont).fillna(False)
dn = ((wret < 0) & cont).fillna(False)
Wk["up_n"] = up.astype(int).groupby([Wk.ticker, (~up).groupby(Wk.ticker).cumsum()]).cumsum()
Wk["dn_n"] = dn.astype(int).groupby([Wk.ticker, (~dn).groupby(Wk.ticker).cumsum()]).cumsum()
Wk["rise"] = (Wk.close / Wk.close.where(~up).groupby(Wk.ticker).ffill() - 1) * 100
Wk["back"] = (Wk.close / Wk.close.where(~dn).groupby(Wk.ticker).ffill() - 1) * 100
gw = Wk.groupby("ticker", sort=False)
okm = (Wk.dn_n >= 2) & (gw.up_n.shift(2) >= 5)
SIG = pd.DataFrame({"ticker": Wk.ticker, "date": Wk.date, "up_n": gw.up_n.shift(2),
                    "rise": gw.rise.shift(2), "back": Wk.back})[okm.fillna(False)]
del Uw, Wk
S8 = SIG[SIG.back > -8]
KEY = U.ticker + U.date
K8 = KEY.isin(set(S8.ticker + S8.date))


def sigmask(z):
    return KEY.isin(set(z.ticker + z.date))


R = Runner(U, UNI, "미장", since=SINCE)
CFG = [
    ("기준선 (눌림 -8% 이내)", K8, 40),
    ("+ 시총 하위50%", K8 & (MQ <= 0.50).fillna(False), 40),
    ("+ 시총 하위50% · 60일", K8 & (MQ <= 0.50).fillna(False), 60),
    ("+ 상승 7주 이상", sigmask(S8[S8.up_n >= 7]), 40),
    ("+ 52주 고점 -5% 이내", K8 & (U.fromhi >= -5).fillna(False), 40),
    ("+ PBR ≤ 3", K8 & (U.PBR <= 3).fillna(False), 40),
    ("+ 눌림 -4% 이내", sigmask(S8[S8.back > -4]), 40),
    ("시총 하위50% + 상승 7주↑", sigmask(S8[S8.up_n >= 7]) & (MQ <= 0.50).fillna(False), 40),
    ("시총 하위50% + PBR ≤ 3", K8 & (MQ <= 0.50).fillna(False) & (U.PBR <= 3).fillna(False), 40),
    ("시총 하위50% + 상승폭 30~100%",
     sigmask(S8[(S8.rise > 30) & (S8.rise <= 100)]) & (MQ <= 0.50).fillna(False), 40),
]

sec("① 다중검정 보정 — %d칸을 돌린 뒤라 이 문턱을 넘어야 한다" % NTRIALS)
print("  %-30s%7s%9s%10s%12s%10s" % ("구성", "월수", "샤프", "문턱샤프", "진짜일확률", "판정"))
RES = {}
for lbl, c, h in CFG:
    m = R.run(lbl, c, hold=h, minn=30, quiet=True)
    if not m:
        print("  %-30s (표본 부족)" % lbl); continue
    RES[lbl] = m
    d = deflated_sharpe(m["Y"].groupby("ym").r.mean(), NTRIALS)
    if not d:
        print("  %-30s (월 수 부족)" % lbl); continue
    m["dsr"] = d["dsr"]
    print("  %-30s%7d%9.3f%10.3f%11.1f%%%10s"
          % (lbl, d["T"], d["sr"], d["sr0"], d["dsr"] * 100,
             "살아남음" if d["dsr"] >= 0.95 else "기각"))

sec("② 최근 해 — 2026 진입분이 음수면 이 집안은 기각한다")
print("  %-30s%8s%9s%9s%8s%10s" % ("구성", "2026 n", "평균", "중앙", "승률", "2025 중앙"))
for lbl in RES:
    Y = RES[lbl]["Y"]
    z6 = Y[Y.yr == "2026"].r
    z5 = Y[Y.yr == "2025"].r
    print("  %-30s%8s%+9.2f%+9.2f%7.0f%%%+10.2f"
          % (lbl, f"{len(z6):,}", z6.mean() if len(z6) else np.nan,
             z6.median() if len(z6) else np.nan,
             (z6 > 0).mean() * 100 if len(z6) else np.nan,
             z5.median() if len(z5) else np.nan))

sec("③ 연도별 중앙값")
print("  %-30s" % "구성" + "".join("%8s" % y for y in range(2016, 2027)))
for lbl in RES:
    Y = RES[lbl]["Y"]
    yr = Y.groupby("yr").r.median()
    row = "".join(("%8.1f" % yr[str(y)]) if str(y) in yr.index else "%8s" % "—"
                  for y in range(2016, 2027))
    print("  %-30s%s" % (lbl, row))

sec("④ 복권형인가 — 상위 5% 기여")
print("  %-30s%8s%9s%9s%12s%10s" % ("구성", "n", "평균", "절삭", "상위5%기여", "최악"))
for lbl in RES:
    v = RES[lbl]["Y"].r
    t5 = v.nlargest(max(1, len(v) // 20)).sum() / v.sum() * 100 if v.sum() else np.nan
    print("  %-30s%8s%+9.2f%+9.2f%11.0f%%%+10.1f"
          % (lbl, f"{len(v):,}", v.mean(), RES[lbl]["trim"], t5, v.min()))

sec("⑤ 시총이 진짜 축인가 — 십분위로 단조인지 (한 칸만 좋으면 우연이다)")
print("  1분위=작은 쪽 · 10분위=큰 쪽 (같은 달 안 순위) · 눌림 -8% 이내 · 40일\n")
print("  %-8s" % "분위" + "".join("%8d" % i for i in range(1, 11)))
med, trim, n = [], [], []
for i in range(10):
    lo, hi = i / 10, (i + 1) / 10 + (0.001 if i == 9 else 0)
    m = R.run("q%d" % (i + 1), K8 & ((MQ > lo) & (MQ <= hi)).fillna(False),
              hold=40, minn=20, quiet=True)
    if not m:
        med.append(np.nan); trim.append(np.nan); n.append(0); continue
    med.append(m["med"]); trim.append(m["trim"]); n.append(m["n"])
f = lambda a: "".join(("%8.2f" % x) if x == x else "%8s" % "—" for x in a)
print("  %-8s%s" % ("중앙", f(med)))
print("  %-8s%s" % ("절삭", f(trim)))
print("  %-8s%s" % ("건수", "".join("%8s" % f"{x:,}" for x in n)))
ok = ~np.isnan(np.array(med, float))
if ok.sum() >= 6:
    rr = np.corrcoef(np.arange(1, 11)[ok], np.array(med, float)[ok])[0, 1]
    print("\n  상관 r = %.2f  →  %s" % (rr, "작은 쪽이 낫다(축 있음)" if rr < -0.4
                                       else ("큰 쪽이 낫다" if rr > 0.4 else "**단조 아님 — 축이 아니다**")))
print("\n총 %.0f초" % (time.time() - t0))
