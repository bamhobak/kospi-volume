# -*- coding: utf-8 -*-
"""**PEAD 조인 판 — 계좌 판정** (2026-09-15).

조이기에서 가장 뚜렷했던 것은 **유동성**이다. 거래대금 문턱을 올릴수록 단조롭게 좋아졌다:

| 유니버스 | n | 중앙 | 절삭 | 상위5%기여 | 2026 | 양수해 |
|---|---|---|---|---|---|---|
| 상위 40%(기준) | 5,009 | +2.81 | +0.49 | 88% | +1.03 | 9/11 |
| 상위 19% | 2,172 | +3.21 | **+1.29** | 74% | +0.69 | 9/11 |
| 상위 9% | 1,063 | +3.66 | **+1.69** | **69%** | +0.69 | 9/11 |

단조롭고 메커니즘도 말이 된다 — 큰 회사의 실적 서프라이즈가 더 믿을 만하고, 실전에서도
유동성이 좋아야 1주씩 사는 미장에서 스프레드를 덜 먹는다. 시총(20억$↑ 절삭 +1.03)과
주가 위치(고점대비 -5%↑ 절삭 +0.91 · 양수해 10/11)도 같은 방향이지만 **서로 상관이 높다**
(큰 회사가 유동성도 좋고 고점 근처일 확률도 높다). 그래서 계좌로 갈라야 한다.

⚠ 오늘 누적 시험 칸이 260개를 넘었다. 조인 판이 계좌에서 **확실히 낫지 않으면 원안을 쓴다.**
   문턱을 바꿔도 비슷하다면 그건 '둔감하다' 는 좋은 신호이지 조일 이유가 아니다.

    python us_pead_acct.py
"""
import glob, pickle, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path
from verdict import block_paths

BASE = Path(__file__).parent
NS = 100
W = 112
SINCE = "20160101"
NM = {"N1": "상승장 신고가", "N2": "낙폭과대", "N3": "저PBR 낙폭", "N4": "자사주 낙폭",
      "N5": "잔잔한 급등주", "PE": "실적 서프라이즈"}
t0 = time.time()


def sec(t):
    print("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


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
A["ret1"] = (A.close / A.groupby("ticker", sort=False).close.shift(1) - 1) * 100
CORE = A.peadq.notna() & (A.peadq >= 0.7) & (A.ret1 >= 3)


def sigs(cond, h=60):
    X = A[cond.fillna(False)].dropna(subset=[f"n{h}"])
    X = X[(X.buy > 0) & (X.date >= SINCE)].sort_values("date")
    keep, last = [], {}
    for t, d_, ix in zip(X.ticker.values, X.date.values, X.index):
        i = DD[d_]
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h
        keep.append(ix)
    Y = X.loc[keep]
    return pd.DataFrame({"date": Y.date.values, "ticker": Y.ticker.values,
                         "ret": Y[f"n{h}"].astype(float).values, "amt20": Y.amt20.values})


CAND = {
    "기준 (거래대금 상위40%)": CORE & (A.amt_q >= 0.60),
    "거래대금 상위 19%": CORE & (A.amt_q >= 0.81),
    "거래대금 상위 9%": CORE & (A.amt_q >= 0.91),
    "시총 20억$↑": CORE & (A.amt_q >= 0.60) & (A.marcap >= 2e9),
    "고점대비 -5%↑": CORE & (A.amt_q >= 0.60) & (A.fromhi >= -5),
    "상위19% & 고점대비 -5%↑": CORE & (A.amt_q >= 0.81) & (A.fromhi >= -5),
}
with open(BASE / "data" / "sector_drop_us_sig.pkl", "rb") as f:
    C = pickle.load(f)
S5, DS, ADI, PCT5 = C["S"], C["DS"], C["ADI"], C["PCT"]
DSS = set(DS)
SIG = {k: sigs(v) for k, v in CAND.items()}
SIG = {k: v[v.date.isin(DSS)].reset_index(drop=True) for k, v in SIG.items()}


def sim(S, PCT, ds, seed=None, cash_cap=1.0, curve=False):
    rng = np.random.default_rng(seed) if seed is not None else None
    nav, held, cnt = 1.0, {}, {}
    byd = {d: gg for d, gg in S[S.date.isin(set(ds))].groupby("date")}
    peak, mdd, inv, cv, log = 1.0, 0.0, [], [], []
    for d in ds:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            nav *= 1 + held.pop(k)[1] / 100
            cnt[k[0]] = cnt.get(k[0], 0) - 1
        peak = max(peak, nav)
        mdd = min(mdd, nav / peak - 1)
        inv.append(sum(PCT[k[0]] for k in held) / 100)
        if curve:
            cv.append((d, nav))
        gg = byd.get(d)
        if gg is None:
            continue
        gg = (gg.sample(frac=1, random_state=int(rng.integers(1 << 30))) if rng is not None
              else gg.sort_values("amt20", ascending=False, na_position="last"))
        for r in gg.itertuples():
            if cnt.get(r.rid, 0) >= r.mx:
                continue
            k = (r.rid, r.ticker, d)
            if k in held:
                continue
            if sum(PCT[x[0]] for x in held) / 100 + r.pct / 100 > cash_cap:
                continue
            held[k] = (di + int(r.hold), r.ret * r.pct / 100)
            cnt[r.rid] = cnt.get(r.rid, 0) + 1
            log.append((r.rid, r.ret, r.pct / 100))
    for v in held.values():
        nav *= 1 + v[1] / 100
    return dict(nav=nav, mdd=mdd * 100, expo=float(np.mean(inv)),
                L=pd.DataFrame(log, columns=["rid", "ret", "amt"]),
                cv=pd.DataFrame(cv, columns=["date", "nav"]) if curve else None)


def build(z, pct=5, mx=3):
    a = pd.DataFrame({"date": z.date.values, "ticker": z.ticker.values,
                      "di": [ADI[d] for d in z.date.values], "rid": "PE",
                      "pct": pct, "mx": mx, "hold": 60, "ret": z.ret.values,
                      "amt20": z.amt20.values})
    P = dict(PCT5); P["PE"] = pct
    return pd.concat([S5, a], ignore_index=True).sort_values("di").reset_index(drop=True), P


sec("① 신호 수 — 조이면 얼마나 줄어드나")
MON = len(DS) / 21
for k, z in SIG.items():
    print("  %-26s%7s건 · 월 %4.1f건" % (k, f"{len(z):,}", len(z) / MON))

sec("② 계좌 (%d시드) — 조인 판이 정말 나은가" % NS)
b = sim(S5, PCT5, DS)
b100 = [sim(S5, PCT5, DS, seed=k) for k in range(NS)]
BN = [x["nav"] for x in b100]
BM = [x["mdd"] for x in b100]
print("  %-26s%7s%9s%9s%12s%9s%9s" % ("구성", "노출", "자산", "낙폭", "시드중앙", "자산승", "낙폭승"))
print("  %-26s%6.0f%%%8.2f배%8.1f%%%11.2f배%9s%9s"
      % ("5규칙 (지금)", b["expo"] * 100, b["nav"], b["mdd"], np.median(BN), "—", "—"))
OUT = {}
for k, z in SIG.items():
    S, P = build(z)
    a = sim(S, P, DS)
    rr = [sim(S, P, DS, seed=j) for j in range(NS)]
    OUT[k] = (S, P, a, rr)
    wn = sum(1 for x, y in zip(rr, b100) if x["nav"] > y["nav"])
    wm = sum(1 for x, y in zip(rr, b100) if x["mdd"] > y["mdd"])
    print("  %-26s%6.0f%%%8.2f배%8.1f%%%11.2f배%7d/%d%7d/%d"
          % ("+" + k, a["expo"] * 100, a["nav"], a["mdd"],
             np.median([x["nav"] for x in rr]), wn, NS, wm, NS))

sec("③ 기준 후보와 조인 후보를 **직접** 짝비교 (같은 시드)")
ref = OUT["기준 (거래대금 상위40%)"][3]
print("  %-26s%12s%9s%9s" % ("구성", "시드중앙", "자산승", "낙폭승"))
for k in list(SIG)[1:]:
    rr = OUT[k][3]
    wn = sum(1 for x, y in zip(rr, ref) if x["nav"] > y["nav"])
    wm = sum(1 for x, y in zip(rr, ref) if x["mdd"] > y["mdd"])
    print("  %-26s%11.2f배%7d/%d%7d/%d"
          % (k + " vs 기준", np.median([x["nav"] for x in rr]), wn, NS, wm, NS))

sec("④ 경로분포")
print("  %-26s%11s%10s%9s%9s%14s%11s"
      % ("", "실제낙폭", "낙폭중앙", "하위5%", "하위1%", "언더워터 하위5%", "자산하위5%"))
a0 = sim(S5, PCT5, DS, curve=True)
m0 = a0["cv"].assign(ym=a0["cv"].date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100
P0 = block_paths(m0, n_paths=5000, mean_block=3)
print("  %-26s%10.1f%%%9.1f%%%8.1f%%%8.1f%%%12.1f년%10.2f배"
      % ("5규칙 (지금)", a0["mdd"], P0.mdd.median(), np.percentile(P0.mdd, 5),
         np.percentile(P0.mdd, 1), np.percentile(P0.under, 95) / 12, np.percentile(P0.nav, 5)))
for k in ("기준 (거래대금 상위40%)", "거래대금 상위 19%", "거래대금 상위 9%"):
    S, P, _, _ = OUT[k]
    a = sim(S, P, DS, curve=True)
    m = a["cv"].assign(ym=a["cv"].date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100
    Pt = block_paths(m, n_paths=5000, mean_block=3)
    print("  %-26s%10.1f%%%9.1f%%%8.1f%%%8.1f%%%12.1f년%10.2f배"
          % ("+" + k, a["mdd"], Pt.mdd.median(), np.percentile(Pt.mdd, 5),
             np.percentile(Pt.mdd, 1), np.percentile(Pt.under, 95) / 12, np.percentile(Pt.nav, 5)))
print("\n총 %.0f초" % (time.time() - t0))
