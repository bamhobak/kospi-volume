# -*- coding: utf-8 -*-
"""**기대감 축으로 조인 N6 — 계좌 판정** (2026-09-15).

가설이 두 이벤트에서 확인됐다(us_hype.py). **이벤트 전에 많이 오른 쪽이 이벤트 뒤에 나쁘다.**

  실적 발표 (미장 · 발표 후 60일 중앙)      지수 편입 (국내 · 편입 후 40일 중앙)
    발표 전 60일 -20%↓ : **+5.32%**          편입 전 60일 0%↓  : -2.41%
    -5 ~ +5%          : +2.22%              0~+20%          : -3.97%
    +20 ~ +50%        : +0.84%              +20~+50%        : -6.05%
    **+50%↑**         : **-1.98%**          **+50%↑**       : **-8.88%**
  둘 다 완벽한 단조. 시장도 이벤트도 다른데 같은 모양이다 — 원리가 있다.

⚠ 이건 사후 선택이 아니다. 가설이 **먼저** 있었고(사용자 제시), 두 이벤트에서 교차 검증됐고,
   단조롭다. 그래서 다른 조이기보다 훨씬 단단하다. 그래도 판정은 계좌다.

규칙 단위로는 조인 판이 압도적이다:
  지금            월 38.7건 · 중앙 +2.82 · 절삭 +0.48 · 상위5%기여 88%
  60일↓0%&상위19%  월  6.3건 · 중앙 +4.57 · 절삭 **+3.09** · 상위5%기여 **55%**

    python us_hype_acct.py
"""
import glob, pickle, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path
from verdict import block_paths

BASE = Path(__file__).parent
NS = 100
W = 116
SINCE = "20160101"
NM = {"N1": "상승장 신고가", "N2": "낙폭과대", "N3": "저PBR 낙폭", "N4": "자사주 낙폭",
      "N5": "잔잔한 급등주", "PE": "실적 서프라이즈"}
t0 = time.time()


def sec(t):
    print("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


A = pd.read_pickle(BASE / "data/us_scan.pkl")
A = A[((~A.pref.fillna(False)) & (A.rawclose >= 3)).fillna(False)]
A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
A["amt_q"] = A.groupby("date").amt20.rank(pct=True)
UNI = (A.amt_q >= 0.6).fillna(False)
cal = np.array(sorted(A.date.unique()))
DD = {d: i for i, d in enumerate(cal)}
g = A.groupby("ticker", sort=False)
A["pre60"] = g.ret60.shift(1)
A["gap"] = (A.close / g.close.shift(1) - 1) * 100

E = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(str(BASE / "data/us/analyst/earn_*.pkl")))],
              ignore_index=True)
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
CORE = (UNI & A.peadq.notna() & (A.peadq >= 0.7) & (A.gap >= 3)).fillna(False)


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
    "지금 (조이기 없음)": CORE,
    "60일↓20%": CORE & (A.pre60 <= 20),
    "60일↓0%": CORE & (A.pre60 <= 0),
    "60일↓20% & 상위19%": CORE & (A.pre60 <= 20) & (A.amt_q >= 0.81),
    "60일↓10% & 상위19%": CORE & (A.pre60 <= 10) & (A.amt_q >= 0.81),
    "60일↓0% & 상위19%": CORE & (A.pre60 <= 0) & (A.amt_q >= 0.81),
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


MON = len(DS) / 21
sec("① 계좌 (%d시드) — 5규칙 기준선 대비" % NS)
b = sim(S5, PCT5, DS)
b100 = [sim(S5, PCT5, DS, seed=k) for k in range(NS)]
BN = [x["nav"] for x in b100]
print("  %-24s%7s%7s%9s%9s%12s%9s%9s"
      % ("구성", "월건수", "노출", "자산", "낙폭", "시드중앙", "자산승", "낙폭승"))
print("  %-24s%7s%6.0f%%%8.2f배%8.1f%%%11.2f배%9s%9s"
      % ("5규칙 (지금)", "—", b["expo"] * 100, b["nav"], b["mdd"], np.median(BN), "—", "—"))
OUT = {}
for k, z in SIG.items():
    S, P = build(z)
    a = sim(S, P, DS)
    rr = [sim(S, P, DS, seed=j) for j in range(NS)]
    OUT[k] = (S, P, a, rr)
    wn = sum(1 for x, y in zip(rr, b100) if x["nav"] > y["nav"])
    wm = sum(1 for x, y in zip(rr, b100) if x["mdd"] > y["mdd"])
    print("  %-24s%6.1f건%6.0f%%%8.2f배%8.1f%%%11.2f배%7d/%d%7d/%d"
          % ("+" + k, len(z) / MON, a["expo"] * 100, a["nav"], a["mdd"],
             np.median([x["nav"] for x in rr]), wn, NS, wm, NS))

sec("② 지금 N6(조이기 없음)과 **직접** 짝비교 — 조여도 계좌가 안 나빠지나")
ref = OUT["지금 (조이기 없음)"][3]
print("  %-24s%12s%9s%9s" % ("구성", "시드중앙", "자산승", "낙폭승"))
for k in list(SIG)[1:]:
    rr = OUT[k][3]
    wn = sum(1 for x, y in zip(rr, ref) if x["nav"] > y["nav"])
    wm = sum(1 for x, y in zip(rr, ref) if x["mdd"] > y["mdd"])
    print("  %-24s%11.2f배%7d/%d%7d/%d"
          % (k, np.median([x["nav"] for x in rr]), wn, NS, wm, NS))

sec("③ 경로분포")
print("  %-24s%11s%10s%9s%9s%14s%11s"
      % ("", "실제낙폭", "낙폭중앙", "하위5%", "하위1%", "언더워터 하위5%", "자산하위5%"))
a0 = sim(S5, PCT5, DS, curve=True)
m0 = a0["cv"].assign(ym=a0["cv"].date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100
P0 = block_paths(m0, n_paths=5000, mean_block=3)
print("  %-24s%10.1f%%%9.1f%%%8.1f%%%8.1f%%%12.1f년%10.2f배"
      % ("5규칙 (지금)", a0["mdd"], P0.mdd.median(), np.percentile(P0.mdd, 5),
         np.percentile(P0.mdd, 1), np.percentile(P0.under, 95) / 12, np.percentile(P0.nav, 5)))
for k in ("지금 (조이기 없음)", "60일↓20% & 상위19%", "60일↓10% & 상위19%", "60일↓0% & 상위19%"):
    S, P, _, _ = OUT[k]
    a = sim(S, P, DS, curve=True)
    m = a["cv"].assign(ym=a["cv"].date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100
    Pt = block_paths(m, n_paths=5000, mean_block=3)
    print("  %-24s%10.1f%%%9.1f%%%8.1f%%%8.1f%%%12.1f년%10.2f배"
          % ("+" + k, a["mdd"], Pt.mdd.median(), np.percentile(Pt.mdd, 5),
             np.percentile(Pt.mdd, 1), np.percentile(Pt.under, 95) / 12, np.percentile(Pt.nav, 5)))
print("\n총 %.0f초" % (time.time() - t0))
