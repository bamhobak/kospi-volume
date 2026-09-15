# -*- coding: utf-8 -*-
"""**PEAD 3차 — 계좌 판정** (2026-09-15).

2차에서 내 의심이 틀렸음이 드러났다.
  · **서프라이즈는 일을 한다** — 발표 전체 대비 초과가 갭만 걸면 +0.40, 서프라이즈까지 걸면
    **+1.06** 으로 2.5배가 된다. '갭만으로도 같으면 장식' 이라는 반증 시도가 실패했다.
  · **단조성도 있다** — 십분위 r = **+0.583**, 1분위 -0.08 → 10분위 +0.96.
    1차에서 '단조성 없음' 이라고 한 건 6구간으로 거칠게 잘라 본 탓이었다.
  · 기준선 걱정도 작았다 — '실적 발표 전체' 는 유니버스 대비 +0.28%p 뿐이다.

가장 좋은 칸: **서프라이즈 상위30% & 발표 다음날 갭 +5%↑ · 60일**
  n=3,504 · 평균 +4.33% · 중앙 +2.88% · 절삭 +0.58% · 승률 57%
  유니버스 대비 +1.35%p · 발표전체 대비 +1.06%p · 그 CI **+0.34**(양수)

약점: **절삭 +0.58% 는 작다**([자사주 낙폭] +4.60 · [저PBR 낙폭] +1.70 에 비하면). 60일이라
자리를 오래 점유한다. 20·40일은 전부 기각이라 60일에서만 나온다.

여기서는 규칙 단위를 넘어 **계좌**로 판정한다.

    python us_pead3.py
"""
import glob, pickle, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path
from verdict import block_paths

BASE = Path(__file__).parent
NS = 100
W = 110
SINCE = "20160101"
NM = {"N1": "상승장 신고가", "N2": "낙폭과대", "N3": "저PBR 낙폭",
      "N4": "자사주 낙폭", "N5": "잔잔한 급등주", "PE": "실적 서프라이즈"}


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
uni = (A.amt_q >= 0.6).fillna(False)
cal = np.array(sorted(A.date.unique()))
DD = {d: i for i, d in enumerate(cal)}


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
g = A.groupby("ticker", sort=False)
A["ret1"] = (A.close / g.close.shift(1) - 1) * 100

CAND = {
    "상위30% & 갭+5% · 60일": (uni & (A.peadq >= 0.7) & (A.ret1 >= 5), 60),
    "상위30% & 갭+3% · 60일": (uni & (A.peadq >= 0.7) & (A.ret1 >= 3), 60),
    "상위10% · 60일": (uni & (A.peadq > 0.9), 60),
    "상위30% & 갭+5% · 40일": (uni & (A.peadq >= 0.7) & (A.ret1 >= 5), 40),
}


def sigs(cond, h):
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


with open(BASE / "data" / "sector_drop_us_sig.pkl", "rb") as f:
    C = pickle.load(f)
S5, DS, ADI, PCT5 = C["S"], C["DS"], C["ADI"], C["PCT"]
DSS = set(DS)


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


sec("① 후보별 신호 — 계좌 구간(2016~) 안")
SIG = {}
for lbl, (c, h) in CAND.items():
    z = sigs(c, h)
    z = z[z.date.isin(DSS)]
    SIG[lbl] = (z, h)
    v = z.ret
    trim = v[v <= v.quantile(0.95)].mean()
    print("  %-26s%7s건 · 평균 %+6.2f%% · 중앙 %+6.2f%% · 승률 %3.0f%% · 절삭 %+5.2f%%"
          % (lbl, f"{len(z):,}", v.mean(), v.median(), (v > 0).mean() * 100, trim))

sec("② 계좌 — 5규칙에 얹으면 (%d시드)" % NS)
b = sim(S5, PCT5, DS)
b100 = [sim(S5, PCT5, DS, seed=k) for k in range(NS)]
BN = [x["nav"] for x in b100]
BM = [x["mdd"] for x in b100]
print("  %-32s%7s%9s%9s%12s%9s%9s" % ("구성", "노출", "자산", "낙폭", "시드중앙", "자산승", "낙폭승"))
print("  %-32s%6.0f%%%8.2f배%8.1f%%%11.2f배%9s%9s"
      % ("5규칙 (지금)", b["expo"] * 100, b["nav"], b["mdd"], np.median(BN), "—", "—"))
BEST = None
for lbl in CAND:
    z, h = SIG[lbl]
    for pct, mx in ((5, 3), (5, 2)):
        add = pd.DataFrame({"date": z.date.values, "ticker": z.ticker.values,
                            "di": [ADI[d] for d in z.date.values], "rid": "PE",
                            "pct": pct, "mx": mx, "hold": h, "ret": z.ret.values,
                            "amt20": z.amt20.values})
        S = pd.concat([S5, add], ignore_index=True).sort_values("di").reset_index(drop=True)
        P = dict(PCT5); P["PE"] = pct
        a = sim(S, P, DS)
        rr = [sim(S, P, DS, seed=k) for k in range(NS)]
        wn = sum(1 for x, y in zip(rr, b100) if x["nav"] > y["nav"])
        wm = sum(1 for x, y in zip(rr, b100) if x["mdd"] > y["mdd"])
        print("  %-32s%6.0f%%%8.2f배%8.1f%%%11.2f배%7d/%d%7d/%d"
              % ("+%s 비중%d자리%d" % (lbl.split(" · ")[0], pct, mx),
                 a["expo"] * 100, a["nav"], a["mdd"],
                 np.median([x["nav"] for x in rr]), wn, NS, wm, NS))
        if BEST is None or wn > BEST[0]:
            BEST = (wn, lbl, pct, mx, S, P, a)

sec("③ 가장 나은 칸 — 경로분포 · 규칙별 · 겹침")
print("  고른 것: %s · 비중%d · 자리%d (자산승 %d/%d)" % (BEST[1], BEST[2], BEST[3], BEST[0], NS))
print("\n  %-24s%11s%10s%9s%9s%14s%11s"
      % ("", "실제낙폭", "낙폭중앙", "하위5%", "하위1%", "언더워터 하위5%", "자산하위5%"))
for lbl, SS, PP in (("5규칙 (지금)", S5, PCT5), ("+실적 서프라이즈", BEST[4], BEST[5])):
    a = sim(SS, PP, DS, curve=True)
    m = a["cv"].assign(ym=a["cv"].date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100
    P = block_paths(m, n_paths=5000, mean_block=3)
    print("  %-24s%10.1f%%%9.1f%%%8.1f%%%8.1f%%%12.1f년%10.2f배"
          % (lbl, a["mdd"], P.mdd.median(), np.percentile(P.mdd, 5), np.percentile(P.mdd, 1),
             np.percentile(P.under, 95) / 12, np.percentile(P.nav, 5)))
L = BEST[6]["L"]
print("\n  %-16s%7s%9s%7s%10s" % ("규칙", "체결", "평균%", "승률", "기여%p"))
for r in ["N1", "N2", "N3", "N4", "N5", "PE"]:
    zz = L[L.rid == r]
    if not len(zz):
        continue
    print("  %-16s%7s%+9.2f%7.0f%%%+10.1f"
          % (NM[r], f"{len(zz):,}", zz.ret.mean(), (zz.ret > 0).mean() * 100,
             (zz.amt * zz.ret / 100).sum() * 100))
S6 = BEST[4]
oi = S6[S6.rid == "PE"]
oo = S6[S6.rid != "PE"]
key = {}
for t, di in zip(oo.ticker.values, oo.di.values):
    key.setdefault(t, []).append(di)
near = sum(1 for t, di in zip(oi.ticker.values, oi.di.values)
           if any(abs(di - x) <= 5 for x in key.get(t, [])))
print("\n  기존 규칙과 같은 종목 ±5일 겹침 %s / %s건 (%.0f%%)"
      % (f"{near:,}", f"{len(oi):,}", near / max(len(oi), 1) * 100))
