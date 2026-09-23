# -*- coding: utf-8 -*-
"""미장 계좌 — [저PBR 낙폭](N3) 보유 40일 vs 60일 (2026-09-24).

n3_tune.py 에서 보유 60일이 두 기간(2009~15 · 2016~) 모두 건별 성적을 올렸다. 그러나 보유가 길어지면
폭락장 실탄이 더 오래 묶이고, 미장 계좌의 제약이 바로 그것이다([[week-reversal-pullback]]) — 같은 시기
[낙폭과대]가 살 돈을 뺏을 수 있다. 그래서 **계좌로** 판정한다([[contrib-not-removal]]).

· 신호: 폐지 포함 패널(us_full_2007.pkl)에서 us_surv_measure.py 의 규칙 정의(폐지 포함판)로 N1~N5,
        [실적 서프라이즈](N6)는 us_drop_n1.py 와 같은 방식(폐지 종목 실적 자료가 없어 생존 종목만).
· 계좌: us_drop_n1.py 의 sim 과 같다 — 규칙별 비중(N1 10 · 나머지 5)·자리(N1 4 · 나머지 3)·현금 한도 100%,
        청산 때 반영(낙폭은 청산 기준이라 실제보다 작게 나온다), 같은 날 순서 무작위 200시드 짝비교.
· 기간: 2016~ · 2009~2015 따로(각각 1.0 에서 시작).

    python us_n3_acct.py
"""
import glob, sys, time, warnings
warnings.filterwarnings("ignore")
DROP = "--drop" in sys.argv
sys.argv = [sys.argv[0], "--panel", "us_full_2007.pkl", "--since", "20090101"]
import io, contextlib
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
NS = 200
t0 = time.time()
_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):           # us_surv_measure 의 표 출력은 버린다 — 규칙 정의만 빌린다
    import us_surv_measure as M
sys.stdout.reconfigure(encoding="utf-8")


def log(m):
    print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


K = M.K
ALL = pd.Series(True, index=K.index)
C = M.rules(ALL, "u_all")
PCT = {"N1": 10, "N2": 5, "N3": 5, "N4": 5, "N5": 5, "N6": 5}
MX = {"N1": 4, "N2": 3, "N3": 3, "N4": 3, "N5": 3, "N6": 3}
HOLD = dict(M.HOLD)
ud = sorted(K.date.unique()); ADI = {d: i for i, d in enumerate(ud)}


def sig(rid, h):
    Z = M.dedup(C[rid], h)
    return pd.DataFrame({"date": Z.date.values, "ticker": Z.ticker.values, "di": Z.di.values, "rid": rid,
                         "hold": h, "ret": Z[f"n{h}"].astype(float).values, "amt20": Z.amt20.values})


log("신호 만드는 중 (N1~N5)")
S = {rid: sig(rid, HOLD[rid]) for rid in ("N1", "N2", "N4", "N5")}
N3_40, N3_60 = sig("N3", 40), sig("N3", 60)

# N6 — 실적 서프라이즈 상위 30% · 발표 다음 거래일 +3% · 거래대금 상위 40% · 60일 (us_drop_n1.py 와 같은 코드)
log("N6 신호 만드는 중")
E = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(str(BASE / "data/us/analyst/*.pkl")))], ignore_index=True)
E["dt"] = pd.to_datetime(E["Earnings Date"], utc=True, errors="coerce")
E = E.dropna(subset=["dt", "Surprise(%)"]).copy()
E["edate"] = E.dt.dt.tz_convert("US/Eastern").dt.strftime("%Y%m%d")
E = E.drop_duplicates(["ticker", "edate"], keep="last")
A = pd.read_pickle(BASE / "data/us_scan.pkl")
A = A[((~A.pref.fillna(False)) & (A.rawclose >= 3)).fillna(False)].sort_values(["ticker", "date"]).reset_index(drop=True)
A["amt_q"] = A.groupby("date").amt20.rank(pct=True)
cal = np.array(sorted(A.date.unique()))
E["bdate"] = [cal[i] if i < len(cal) else None for i in np.searchsorted(cal, E.edate.values, "right")]
E = E.dropna(subset=["bdate"])
E["sur"] = E["Surprise(%)"].astype(float)
E["q"] = E.groupby("bdate").sur.rank(pct=True)
E = E[E.groupby("bdate").sur.transform("size") >= 5]
A["peadq"] = (A.ticker + A.date).map(dict(zip(E.ticker + E.bdate, E.q)))
A["ret1"] = (A.close / A.groupby("ticker", sort=False).close.shift(1) - 1) * 100
X = A[((A.amt_q >= 0.6) & (A.peadq >= 0.7) & (A.ret1 >= 3)).fillna(False)].dropna(subset=["n60"])
X = X[(X.buy > 0) & X.date.isin(ADI)].sort_values("date")
keep, last = [], {}
for t, d_, ix in zip(X.ticker.values, X.date.values, X.index):
    i = ADI[d_]
    if last.get(t, -10 ** 9) >= i:
        continue
    last[t] = i + 60
    keep.append(ix)
Y = X.loc[keep]
S["N6"] = pd.DataFrame({"date": Y.date.values, "ticker": Y.ticker.values, "di": [ADI[d] for d in Y.date.values],
                        "rid": "N6", "hold": 60, "ret": Y.n60.astype(float).values, "amt20": Y.amt20.values})
del A, E, X, Y
for r, z in {**S, "N3(40)": N3_40, "N3(60)": N3_60}.items():
    log(f"  {r} {len(z):,}건")


def sim(T, days, seed):
    """us_drop_n1.py 의 sim 과 같은 규칙 — 청산 때 반영, 규칙별 자리·비중, 현금 한도 100%."""
    rng = np.random.default_rng(seed)
    nav, held, cnt = 1.0, {}, {}
    byd = {d: g for d, g in T.groupby("date")}
    peak, mdd, inv = 1.0, 0.0, []
    for d in days:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            nav *= 1 + held.pop(k)[1] / 100
            cnt[k[0]] -= 1
        peak = max(peak, nav); mdd = min(mdd, nav / peak - 1)
        inv.append(sum(PCT[k[0]] for k in held) / 100)
        g = byd.get(d)
        if g is None:
            continue
        g = g.sample(frac=1, random_state=int(rng.integers(1 << 30)))
        for r in g.itertuples():
            if cnt.get(r.rid, 0) >= MX[r.rid]:
                continue
            k = (r.rid, r.ticker, d)
            if k in held or sum(PCT[x[0]] for x in held) / 100 + PCT[r.rid] / 100 > 1.0:
                continue
            held[k] = (di + int(r.hold), r.ret * PCT[r.rid] / 100)
            cnt[r.rid] = cnt.get(r.rid, 0) + 1
    for v in held.values():
        nav *= 1 + v[1] / 100
    yrs = len(days) / 252
    return nav, (nav ** (1 / yrs) - 1) * 100, mdd * 100, float(np.mean(inv)) * 100


_vs = "빼기" if DROP else "보유 60일"
print(f"\n## 미장 계좌 — [저PBR 낙폭] 보유 40일 vs {_vs} ({NS}시드 짝비교 · 폐지 포함 신호)\n")
print("| 기간 | 안 | 최종 배수(중앙) | 연수익 | 최대낙폭(청산 기준) | 평균 투입 | 바꾼 쪽이 이긴 시드 — 최종 | — 낙폭 |")
print("|---|---|---|---|---|---|---|---|")
for per, lo, hi in (("2016~", "20160101", "20991231"), ("2009~2015", "20090101", "20151231")):
    days = [d for d in ud if lo <= d <= hi]
    base = pd.concat([*S.values(), N3_40], ignore_index=True)
    # --drop: 60일 대신 [저PBR 낙폭]을 아예 뺀 계좌와 견준다(다른 규칙의 비중·자리는 그대로)
    alt = pd.concat([*S.values()] + ([] if DROP else [N3_60]), ignore_index=True)
    base = base[(base.date >= lo) & (base.date <= hi)]; alt = alt[(alt.date >= lo) & (alt.date <= hi)]
    R0 = np.array([sim(base, days, s) for s in range(NS)])
    R1 = np.array([sim(alt, days, s) for s in range(NS)])
    w_nav = (R1[:, 0] > R0[:, 0]).mean() * 100
    w_mdd = (R1[:, 2] > R0[:, 2]).mean() * 100
    for nm, R, extra in (("보유 40일(지금)", R0, "| — | — |"), ("저PBR 낙폭 빼기" if DROP else "보유 60일", R1, f"| {w_nav:.0f}% | {w_mdd:.0f}% |")):
        print(f"| {per} | {nm} | {np.median(R[:, 0]):.2f}배 | {np.median(R[:, 1]):+.1f}% | {np.median(R[:, 2]):.1f}% | "
              f"{np.median(R[:, 3]):.0f}% {extra}")
    log(f"  {per} 끝")

# 60일로 바꾸면 [낙폭과대]가 못 산 건이 늘어나는가 — 폭락장 실탄 경쟁 확인(시드 0)
log(f"끝 ({(time.time() - t0) / 60:.1f}분)")
