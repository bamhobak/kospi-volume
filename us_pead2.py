# -*- coding: utf-8 -*-
"""**PEAD 2차 — 서프라이즈가 정말 일을 하는가** (2026-09-15).

1차에서 42칸 중 10칸이 통과했다. 그런데 통과한 모양이 이상하다.

  · **전부 60일**이다. 20일·40일은 한 칸도 없다.
  · **단조성이 없다** — 서프라이즈 상위10% 중앙 +2.02% 인데 **중간 40~60% 가 +2.32%** 로 더 높다.
  · **반대 조건도 통과한다** — '좋은 실적인데 시장이 무시(갭 음수)' 도 ✅.
  · **선별 없는 대조군**('실적 발표 전체 · 60일')이 중앙 +1.82% · 초과 +0.28%p 로 거의 붙는다.

이 넷을 합치면 가설이 이렇게 바뀐다 — **PEAD(서프라이즈 크기에 따른 표류)가 아니라,
그냥 '실적을 발표하는 종목을 60일 들면 유니버스보다 조금 낫다' 일 뿐이다.**
그건 선별이 아니라 생존·유동성 편향일 수 있다.

그래서 결정적 대조를 세운다.
  ① **기준선을 유니버스가 아니라 '실적 발표 전체'로** 바꿔 초과를 다시 잰다
  ② **서프라이즈를 빼고 갭만으로** 골라 본다 — 같은 성적이면 서프라이즈는 장식이다
  ③ 단조성 검정 — 십분위로 잘라 기울기를 본다
  ④ 60일만 되는 게 정상인가 — 보유일을 더 늘려 본다

    python us_pead2.py
"""
import glob, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from vp_lib import Runner, hdr, log, BASE, boot_ci

SINCE = "20160101"
W = 152

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
uni = (A.amt_q >= 0.6).fillna(False)
cal = np.array(sorted(A.date.unique()))


def nextday(s):
    i = np.searchsorted(cal, s, "right")
    return cal[i] if i < len(cal) else None


E["bdate"] = [nextday(d) for d in E.edate.values]
E = E.dropna(subset=["bdate"])
E["sur"] = E["Surprise(%)"].astype(float)
E["q"] = E.groupby("bdate").sur.rank(pct=True)
E["n_day"] = E.groupby("bdate").sur.transform("size")
E = E[E.n_day >= 5]

A["_k"] = A.ticker + A.date
A["peadq"] = A._k.map(dict(zip(E.ticker + E.bdate, E.q)))
has = A.peadq.notna()
g = A.groupby("ticker", sort=False)
A["ret1"] = (A.close / g.close.shift(1) - 1) * 100
log(f"실적 이벤트 {int(has.sum()):,}행 (유니버스 안 {int((has & uni).sum()):,})")

R = Runner(A, uni, "us", since=SINCE)
HOLDS = (20, 40, 60)   # us_scan 에는 n5·n10·n20·n40·n60 만 있다


# ── ① 기준선을 '실적 발표 전체' 로 바꿔 초과를 다시 잰다 ──────────────────
def vs_earn(tag, cond, h):
    """유니버스가 아니라 **같은 날 실적을 발표한 종목 전체**를 기준선으로 쓴다."""
    col = f"n{h}"
    base = A[(has & uni).fillna(False)].dropna(subset=[col])
    base = base[base.date >= SINCE]
    ben = base.groupby("date")[col].mean()
    X = A[(cond & uni).fillna(False)].dropna(subset=[col])
    X = X[X.date >= SINCE].sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h
        keep.append(ix)
    Y = X.loc[keep].copy()
    if len(Y) < 40:
        print(f"  {tag:<44}{len(Y):>6} (부족)")
        return None
    Y["r"] = Y[col].astype(float)
    Y["exu"] = Y.r - Y.date.map(R.bench(h))          # 유니버스 대비
    Y["exe"] = Y.r - Y.date.map(ben)                 # 실적 발표 전체 대비
    ci = boot_ci(Y.assign(ym=Y.date.str[:6]).groupby("ym").exe.mean())
    trim = Y.r[Y.r <= Y.r.quantile(0.95)].mean()
    print(f"  {tag:<44}{len(Y):>6}{Y.r.mean():>8.2f}{Y.r.median():>8.2f}{trim:>8.2f}"
          f"{(Y.r > 0).mean() * 100:>6.0f}%{Y.exu.mean():>9.2f}{Y.exe.mean():>10.2f}{ci:>9.2f}")
    return Y.exe.mean(), ci


print("\n" + "=" * W)
print("PEAD 2차 — 기준선을 '같은 날 실적 발표 종목 전체' 로 바꾼다")
print("=" * W)
print(f"  {'조건':<44}{'n':>6}{'평균':>8}{'중앙':>8}{'절삭':>8}{'승률':>7}"
      f"{'유니버스대비':>9}{'발표전체대비':>10}{'그 CI':>9}")
print("\n  [기준선 자체]")
for h in HOLDS:
    vs_earn(f"실적 발표 전체 · {h}일", has, h)

print("\n  [① 서프라이즈로 고르면 — 발표 전체보다 나은가]")
for lo, lbl in [(0.9, "서프라이즈 상위 10%"), (0.7, "상위 30%"), (0.5, "상위 50%")]:
    for h in HOLDS:
        vs_earn(f"{lbl} · {h}일", has & (A.peadq > lo), h)

print("\n  [② 서프라이즈를 빼고 **갭만** 으로 — 같은 성적이면 서프라이즈는 장식이다]")
for lo in (3, 5):
    for h in HOLDS:
        vs_earn(f"발표 다음날 갭 +{lo}%↑ (서프라이즈 무관) · {h}일", has & (A.ret1 >= lo), h)
print("\n  [비교: 서프라이즈까지 걸면]")
for lo in (3, 5):
    for h in HOLDS:
        vs_earn(f"서프라이즈 상위30% & 갭 +{lo}%↑ · {h}일", has & (A.peadq >= 0.7) & (A.ret1 >= lo), h)

print("\n" + "=" * W)
print("③ 단조성 — 서프라이즈 십분위별 (60일). 기울기가 있어야 PEAD 다")
print("=" * W)
print(f"  {'십분위':<12}{'n':>7}{'평균':>9}{'중앙':>9}{'절삭':>9}{'승률':>7}{'발표전체대비':>12}")
col = "n60"
base = A[(has & uni).fillna(False)].dropna(subset=[col])
base = base[base.date >= SINCE]
ben = base.groupby("date")[col].mean()
rows = []
for i in range(10):
    lo, hi = i / 10, (i + 1) / 10 + (0.001 if i == 9 else 0)
    c = has & (A.peadq > lo) & (A.peadq <= hi)
    X = A[(c & uni).fillna(False)].dropna(subset=[col])
    X = X[X.date >= SINCE].sort_values("di")
    keep, last = [], {}
    for t, ii, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= ii:
            continue
        last[t] = ii + 60
        keep.append(ix)
    Y = X.loc[keep].copy()
    Y["r"] = Y[col].astype(float)
    ex = (Y.r - Y.date.map(ben)).mean()
    trim = Y.r[Y.r <= Y.r.quantile(0.95)].mean()
    rows.append((i + 1, len(Y), Y.r.mean(), Y.r.median(), trim, (Y.r > 0).mean() * 100, ex))
    print(f"  {i+1:>2}분위{'':<6}{len(Y):>7,}{Y.r.mean():>9.2f}{Y.r.median():>9.2f}{trim:>9.2f}"
          f"{(Y.r > 0).mean() * 100:>6.0f}%{ex:>12.2f}")
D = pd.DataFrame(rows, columns=["q", "n", "mean", "med", "trim", "win", "ex"])
r_ = np.corrcoef(D.q, D.ex)[0, 1]
print(f"\n  분위 ↔ 발표전체대비 초과 상관 r = {r_:+.3f}")
print(f"  1분위(최악) {D.ex.iloc[0]:+.2f} → 10분위(최고) {D.ex.iloc[-1]:+.2f}  "
      f"(차이 {D.ex.iloc[-1] - D.ex.iloc[0]:+.2f}%p)")
print("  ※ PEAD 가 진짜면 r 이 뚜렷한 양수여야 한다. 0 근처면 서프라이즈는 일을 안 하는 것이다.")
