# -*- coding: utf-8 -*-
"""**[실적 서프라이즈]에 하락장 게이트를 걸까** (us_n6_regime.py 후속, 2026-09-16).

거래별로는 격차가 크다.
  상승 국면 3,704건 · 중앙 +1.63 · 승률 54% · **절삭 -0.75** · 상위5%기여 **125%**(복권형)
  하락 국면 1,305건 · 중앙 +6.13 · 승률 65% · **절삭 +4.03** · 상위5%기여 47%
  하락 국면은 잰 10해 전부 양수, 상승 국면은 7/11.

⚠ 그런데 바로 어제 같은 모양에서 뒤집혔다([[us-drop-n1-reject]]).
   [상승장 신고가]도 절삭 -0.39 · 상위5%기여 126% 로 복권형인데, 계좌가 실제로 사는
   225건만 보면 평균 +3.23% 로 6규칙 중 2위였다. **자리 경쟁(거래대금 큰 순)이
   이미 좋은 쪽을 골라내고 있어서** 규칙 전체의 분포와 계좌가 먹는 분포가 다르다.

그리고 하락 게이트를 걸면 신호가 5,009 → 1,305건으로 **4분의 1**이 된다.
미장은 병목이 자리가 아니라 후보라([[slot-lab]]) 노출이 빌 위험이 크다.

  ① 계좌 — 하락 전용 / 상승 쪽만 비중 낮추기 / 자리 나누기 (200시드)
  ② 계좌가 실제로 산 N6 를 국면별로 — 규칙 분포와 같은가 다른가
  ③ 경로분포
  ④ 노출 — 하락 게이트를 걸면 상승장에 뭐가 남나

    python us_n6_gate.py
"""
import glob, pickle, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path
from verdict import block_paths

BASE = Path(__file__).parent
NS = 200
W = 118
SINCE = "20160101"
NM = {"N1": "상승장 신고가", "N2": "낙폭과대", "N3": "저PBR 낙폭", "N4": "자사주 낙폭",
      "N5": "잔잔한 급등주", "N6": "실적 서프라이즈", "N7": "실적(상승장)"}
t0 = time.time()


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def sec(t):
    print("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


log("국면 — S&P500 60일선 (us_verify.py 와 같은 방식)")
import FinanceDataReader as fdr
IX = fdr.DataReader("US500", "2004-06-01")
IX = IX[IX.Close > 0].copy()
IX["date"] = IX.index.strftime("%Y%m%d")
IX["ma60"] = IX.Close.rolling(60).mean()
# numpy bool 은 `is True` 가 False 라 파이썬 bool 로 바꿔 둔다
UP = {d: bool(v) for d, v in zip(IX.date, (IX.Close > IX.ma60).values)}

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
PE = pd.DataFrame({"date": Y.date.values, "ticker": Y.ticker.values,
                   "ret": Y.n60.astype(float).values, "amt20": Y.amt20.values})
del A, X, Y

with open(BASE / "data" / "sector_drop_us_sig.pkl", "rb") as f:
    C = pickle.load(f)
S5, DS, ADI, PCT5 = C["S"], C["DS"], C["ADI"], C["PCT"]
PE = PE[PE.date.isin(set(DS))].reset_index(drop=True)
S6 = pd.concat([S5, pd.DataFrame({"date": PE.date.values, "ticker": PE.ticker.values,
                                  "di": [ADI[d] for d in PE.date.values], "rid": "N6",
                                  "pct": 5, "mx": 3, "hold": 60, "ret": PE.ret.values,
                                  "amt20": PE.amt20.values})],
               ignore_index=True).sort_values("di").reset_index(drop=True)
S6["up"] = S6.date.map(UP)
PCT6 = dict(PCT5)
PCT6["N6"] = 5
NMON = len(set(d[:6] for d in DS))
log("  N6 %s건 (상승 %.0f%% · 하락 %.0f%%)"
    % (f"{len(PE):,}", S6[S6.rid == 'N6'].up.mean() * 100, (~S6[S6.rid == 'N6'].up).mean() * 100))


def variant(mode=None, pct=None, mx=None):
    """mode: 'dn' 하락 전용 · 'split' 국면별로 비중을 다르게(상승분을 N7 로 쪼갬)."""
    z = S6.copy()
    P = dict(PCT6)
    if mode == "dn":
        z = z[~((z.rid == "N6") & z.up)]
    elif mode == "split":
        # 상승 국면 N6 를 별도 규칙 N7 로 떼어내 비중·자리를 따로 준다
        m = (z.rid == "N6") & z.up
        z.loc[m, "rid"] = "N7"
        z.loc[m, "pct"] = pct.get("N7", 3) if pct else 3
        z.loc[m, "mx"] = mx.get("N7", 2) if mx else 2
        P["N7"] = pct.get("N7", 3) if pct else 3
    if pct:
        for k, v in pct.items():
            if k == "N7" and mode == "split":
                continue
            z.loc[z.rid == k, "pct"] = v
            P[k] = v
    if mx:
        for k, v in mx.items():
            if k == "N7" and mode == "split":
                continue
            z.loc[z.rid == k, "mx"] = v
    return z.reset_index(drop=True), P


def sim(S, PCT, seed=None, cash_cap=1.0, curve=False):
    rng = np.random.default_rng(seed) if seed is not None else None
    nav, held, cnt = 1.0, {}, {}
    byd = {d: gg for d, gg in S[S.date.isin(set(DS))].groupby("date")}
    peak, mdd, inv, cv, lg = 1.0, 0.0, [], [], []
    for d in DS:
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
            if k in held or sum(PCT[x[0]] for x in held) / 100 + r.pct / 100 > cash_cap:
                continue
            held[k] = (di + int(r.hold), r.ret * r.pct / 100)
            cnt[r.rid] = cnt.get(r.rid, 0) + 1
            lg.append((r.rid, d, r.ret, r.pct / 100, bool(UP.get(d, False))))
    for v in held.values():
        nav *= 1 + v[1] / 100
    return dict(nav=nav, mdd=mdd * 100, expo=float(np.mean(inv)),
                L=pd.DataFrame(lg, columns=["rid", "date", "ret", "amt", "up"]),
                cv=pd.DataFrame(cv, columns=["date", "nav"]) if curve else None)


sec("① 계좌 — 하락장 게이트를 걸면 (%d시드 짝비교)" % NS)
BS, BP = variant()
b = [sim(BS, BP, seed=k) for k in range(NS)]
BN = np.array([x["nav"] for x in b])
BM = np.array([x["mdd"] for x in b])
log("  기준선 끝")
CFG = [("지금 (게이트 없음)", dict()),
       ("하락 전용", dict(mode="dn")),
       ("하락 전용 · 비중 10", dict(mode="dn", pct={"N6": 10})),
       ("하락 전용 · 10/자리5", dict(mode="dn", pct={"N6": 10}, mx={"N6": 5})),
       ("국면별 쪼갬 (하락5·상승3)", dict(mode="split", pct={"N6": 5, "N7": 3})),
       ("국면별 쪼갬 (하락8·상승3)", dict(mode="split", pct={"N6": 8, "N7": 3})),
       ("국면별 쪼갬 (하락8·상승2)", dict(mode="split", pct={"N6": 8, "N7": 2}))]
print("  %-26s%8s%7s%9s%9s%11s%10s%9s"
      % ("구성", "신호", "노출", "자산", "낙폭", "시드중앙", "자산승", "낙폭승"))
OUT = {}
for lbl, kw in CFG:
    S, P = variant(**kw)
    a = sim(S, P)
    rr = [sim(S, P, seed=k) for k in range(NS)]
    n = np.array([x["nav"] for x in rr])
    m = np.array([x["mdd"] for x in rr])
    OUT[lbl] = (S, P, a, n, m)
    n6 = int(((S.rid == "N6") | (S.rid == "N7")).sum())
    if not kw:
        print("  %-26s%8s%6.0f%%%8.2f배%8.1f%%%10.2f배%10s%9s"
              % (lbl, f"{n6:,}", a["expo"] * 100, a["nav"], a["mdd"], np.median(n), "—", "—"))
    else:
        print("  %-26s%8s%6.0f%%%8.2f배%8.1f%%%10.2f배%7d/%d%6d/%d"
              % (lbl, f"{n6:,}", a["expo"] * 100, a["nav"], a["mdd"], np.median(n),
                 (n > BN).sum(), NS, (m > BM).sum(), NS))
    log("  %s 끝" % lbl)
print("\n  ※ %d/%d 이 동전이다." % (NS // 2, NS))

sec("② 계좌가 실제로 산 N6 — 규칙 전체 분포와 같은가")
print("  (규칙 전체: 상승 3,704건 중앙 +1.63 절삭 -0.75 / 하락 1,305건 중앙 +6.13 절삭 +4.03)")
L = OUT["지금 (게이트 없음)"][2]["L"]
z = L[L.rid == "N6"]
print("\n  %-14s%9s%9s%9s%8s%9s" % ("국면", "체결", "평균%", "중앙%", "승률", "절삭평균"))
for lbl, m in (("상승 국면", True), ("하락 국면", False)):
    v = z[z.up == m].ret.astype(float)
    if len(v) < 5:
        continue
    tr = v[v <= v.quantile(0.95)].mean() if len(v) > 20 else v.mean()
    print("  %-14s%9s%+9.2f%+9.2f%7.0f%%%+9.2f"
          % (lbl, f"{len(v):,}", v.mean(), v.median(), (v > 0).mean() * 100, tr))
print("\n  ※ 여기서 상승 국면이 규칙 전체보다 훨씬 좋으면 [상승장 신고가]와 같은 얘기다 —")
print("    자리 경쟁이 이미 좋은 쪽을 골라내고 있어 게이트를 더 걸 이유가 없다.")

sec("③ 경로분포")
print("  %-26s%10s%10s%9s%9s%14s%11s"
      % ("", "실제낙폭", "낙폭중앙", "하위5%", "하위1%", "언더워터 하위5%", "자산하위5%"))
for lbl in ("지금 (게이트 없음)", "하락 전용", "하락 전용 · 10/자리5", "국면별 쪼갬 (하락8·상승3)"):
    S, P, _, _, _ = OUT[lbl]
    a = sim(S, P, curve=True)
    mm = a["cv"].assign(ym=a["cv"].date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100
    Pt = block_paths(mm, n_paths=5000, mean_block=3)
    print("  %-26s%9.1f%%%9.1f%%%8.1f%%%8.1f%%%12.1f년%10.2f배"
          % (lbl, a["mdd"], Pt.mdd.median(), np.percentile(Pt.mdd, 5),
             np.percentile(Pt.mdd, 1), np.percentile(Pt.under, 95) / 12,
             np.percentile(Pt.nav, 5)))

sec("④ 노출 — 하락 게이트를 걸면 상승장에 뭐가 남나")
for lbl in ("지금 (게이트 없음)", "하락 전용"):
    S, P, a, _, _ = OUT[lbl]
    L = a["L"]
    print("\n  [%s]  노출 %.0f%%" % (lbl, a["expo"] * 100))
    print("    %-16s%8s%9s%8s%11s%11s" % ("규칙", "체결", "평균%", "승률", "기여%p", "월 체결"))
    for r in ["N1", "N2", "N3", "N4", "N5", "N6", "N7"]:
        zz = L[L.rid == r]
        if not len(zz):
            continue
        print("    %-16s%8s%+9.2f%7.0f%%%+11.1f%10.1f건"
              % (NM[r], f"{len(zz):,}", zz.ret.mean(), (zz.ret > 0).mean() * 100,
                 (zz.amt * zz.ret / 100).sum() * 100, len(zz) / NMON))
print("\n총 %.0f초" % (time.time() - t0))
