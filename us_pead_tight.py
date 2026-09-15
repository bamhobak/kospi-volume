# -*- coding: utf-8 -*-
"""**PEAD 조이기 — 규칙에 넣기 전 마지막 다듬기** (2026-09-15).

채택 방향으로 정해진 후보: **서프라이즈 상위30% & 발표 다음날 갭 +3%↑ · 60일**
  5,009건 · 평균 +3.95% · 중앙 +2.81% · 승률 57% · 절삭 +0.49% · 초과 +1.11%p
  상위5% 기여 88% · **2026 +1.0%** · 양수해 9/11

갭 +5% 판은 평균이 높지만 **2026 -0.7%** 라 탈락시켰다(최근 해는 필수 기준).

여기서 훑는 축 — 이미 판 것(서프라이즈 백분위·갭·보유일)은 이웃만 확인하고,
**안 판 것**에 무게를 둔다.
  ① 갭 이웃 (+2 ~ +6%) · 서프라이즈 문턱 이웃
  ② **발표일에 시장이 끝까지 믿었나** — 갭 뜨고 종가가 시가 위에서 마감
  ③ **거래량이 실렸나** ⚠ 우리 경험상 '거래량 실릴수록 좋다' 는 대개 역방향이다
  ④ 주가 위치 — 신고가 근처 vs 낙폭 상태에서의 서프라이즈
  ⑤ 시총·유동성·국면
  ⑥ 유망한 둘을 겹치기

판정: 절삭>0 · 상위5%기여<100% · **2026 중앙>0** · 양수해≥8/11 · 신호≥800
  (지금 후보가 이미 다 넘으므로, **지금보다 나아야** 의미가 있다)

    python us_pead_tight.py
"""
import glob, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
W = 150
SINCE = "20160101"
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
A["pclose"] = g.close.shift(1)
A["ret1"] = (A.close / A.pclose - 1) * 100
# 발표 다음날: 시가 대비 종가 (시장이 끝까지 믿었나). buy = 그 전날 행의 '익일 시가' 라
# 같은 행의 시가는 전날 buy 다.
A["dayopen"] = g.buy.shift(1)
A["intraday"] = (A.close / A.dayopen - 1) * 100
A["volx"] = A.volume / g.volume.transform(lambda s: s.shift(1).rolling(20).mean())
BEN = {h: A[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in (40, 60)}
HAS = A.peadq.notna()
BASECOND = (UNI & HAS & (A.peadq >= 0.7) & (A.ret1 >= 3)).fillna(False)
log("  실적 이벤트 %s · 후보 %s행" % (f"{int(HAS.sum()):,}", f"{int(BASECOND.sum()):,}"))


def run(tag, cond, h=60, minn=400):
    z = A[cond.fillna(False)].dropna(subset=[f"n{h}"])
    z = z[(z.buy > 0) & (z.date >= SINCE)].sort_values("date")
    keep, last = [], {}
    for t, d_, ix in zip(z.ticker.values, z.date.values, z.index):
        i = DD[d_]
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h
        keep.append(ix)
    Y = z.loc[keep].copy()
    if len(Y) < minn:
        print("  %-42s%6s (부족)" % (tag, f"{len(Y):,}"))
        return None
    v = Y[f"n{h}"].astype(float)
    Y["r"] = v
    ex = (v - Y.date.map(BEN[h])).mean()
    trim = v[v <= v.quantile(0.95)].mean()
    t5 = v.nlargest(max(1, len(v) // 20)).sum() / v.sum() * 100 if v.sum() != 0 else np.nan
    yr = Y.assign(y=Y.date.str[:4]).groupby("y").r.median()
    y26 = yr.get("2026", np.nan)
    pos = int((yr > 0).sum())
    ok = (trim > 0) and (t5 < 100) and (y26 > 0) and (pos >= 8)
    print("  %-42s%6s%8.2f%8.2f%7.0f%%%8.2f%8.2f%8.0f%%%8.2f%6d/%d %s"
          % (tag, f"{len(Y):,}", v.mean(), v.median(), (v > 0).mean() * 100, trim, ex, t5,
             y26, pos, len(yr), "  ✅" if ok else ""))
    return dict(tag=tag, n=len(Y), mean=v.mean(), med=v.median(), trim=trim, ex=ex,
                t5=t5, y26=y26, pos=pos, ok=ok)


HDR = ("  %-42s%6s%8s%8s%7s%8s%8s%8s%8s%8s" %
       ("조건", "n", "평균", "중앙", "승률", "절삭", "초과", "상위5%", "2026", "양수해"))


def sec(t):
    print("\n## " + t)
    print(HDR)


print("\n" + "=" * W)
print("PEAD 조이기 — 기준: 서프라이즈 상위30% & 갭 +3%↑ · 60일")
print("판정: 절삭>0 · 상위5%기여<100% · 2026중앙>0 · 양수해≥8/11 · n≥400")
print("=" * W)
hits = []

sec("기준선")
BASE_R = run("지금 후보 (상위30% & 갭+3%)", BASECOND)

sec("① 갭·서프라이즈 문턱 이웃")
for gp in (2, 3, 4, 5, 6):
    run("갭 +%d%%↑ (서프라이즈 상위30%%)" % gp, UNI & HAS & (A.peadq >= 0.7) & (A.ret1 >= gp))
for q in (0.5, 0.6, 0.8, 0.9):
    run("서프라이즈 상위 %d%% & 갭+3%%" % int((1 - q) * 100),
        UNI & HAS & (A.peadq >= q) & (A.ret1 >= 3))

sec("② 발표일에 시장이 끝까지 믿었나 — 갭 뜨고 종가가 시가 위")
r = run("+ 종가 > 시가 (끝까지 올랐다)", BASECOND & (A.intraday > 0))
if r and r["ok"]:
    hits.append(r)
r = run("+ 종가 < 시가 (갭 뜨고 밀렸다)", BASECOND & (A.intraday < 0))
if r and r["ok"]:
    hits.append(r)
for lo in (1, 2):
    r = run("+ 종가가 시가보다 %d%%↑ 위" % lo, BASECOND & (A.intraday >= lo))
    if r and r["ok"]:
        hits.append(r)

sec("③ 거래량이 실렸나 ⚠ 우리 경험상 대개 역방향이다")
for lo in (1.5, 2, 3):
    r = run("+ 거래량 20일평균의 %.1f배↑" % lo, BASECOND & (A.volx >= lo))
    if r and r["ok"]:
        hits.append(r)
r = run("+ 거래량 20일평균 이하 (안 실렸다)", BASECOND & (A.volx <= 1.0))
if r and r["ok"]:
    hits.append(r)

sec("④ 주가 위치")
for lo in (-50, -30, -15, -5):
    r = run("+ 고점대비 %d%% 이상" % lo, BASECOND & (A.fromhi >= lo))
    if r and r["ok"]:
        hits.append(r)
r = run("+ 고점대비 -30% 미만 (낙폭 상태)", BASECOND & (A.fromhi < -30))
if r and r["ok"]:
    hits.append(r)
for lo in (-10, 0, 10):
    r = run("+ 60일 수익 %d%% 이상" % lo, BASECOND & (A.ret60 >= lo))
    if r and r["ok"]:
        hits.append(r)

sec("⑤ 시총·유동성·국면")
for v in (5e8, 2e9, 1e10):
    r = run("+ 시총 %.0f억$ 이상" % (v / 1e8), BASECOND & (A.marcap >= v))
    if r and r["ok"]:
        hits.append(r)
for q in (0.8, 0.9):
    r = run("+ 거래대금 상위 %d%%" % int((1 - q) * 100), BASECOND & (A.amt_q >= q))
    if r and r["ok"]:
        hits.append(r)
if "up" in A.columns:
    r = run("+ 상승장(S&P 60일선 위)", BASECOND & (A.up == True))
    if r and r["ok"]:
        hits.append(r)
    r = run("+ 하락장", BASECOND & (A.up == False), minn=200)
    if r and r["ok"]:
        hits.append(r)

sec("⑥ 보유일 — 40 vs 60")
run("지금 후보 · 40일", BASECOND, h=40)

print("\n" + "=" * W)
if BASE_R:
    print("기준 후보: 중앙 %+.2f%% · 절삭 %+.2f%% · 상위5%% %.0f%% · 2026 %+.2f%% · 양수해 %d/%d"
          % (BASE_R["med"], BASE_R["trim"], BASE_R["t5"], BASE_R["y26"], BASE_R["pos"], 11))
print("판정 통과 %d개 — 그중 **기준보다 나은 것**만 의미가 있다" % len(hits))
for r in hits:
    better = (BASE_R is None) or (r["trim"] > BASE_R["trim"] and r["med"] > BASE_R["med"])
    print("  %s %-42s n=%-6s 중앙 %+.2f · 절삭 %+.2f · 상위5%% %.0f%% · 2026 %+.2f"
          % ("★" if better else " ", r["tag"], f"{r['n']:,}", r["med"], r["trim"], r["t5"], r["y26"]))
print("총 %.0f초" % (time.time() - t0))
