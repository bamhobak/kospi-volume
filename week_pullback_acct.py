# -*- coding: utf-8 -*-
"""**주봉 눌림목 — 계좌 판정** (week_pullback3.py 후속, 2026-09-16).

규칙 단위로는 **다중검정에서 기각**됐다(최고 88.8% · 문턱 95%). 그런데 이 집안은
규칙 단위와 계좌 판정이 **양쪽으로** 갈리는 걸 여러 번 봤다([[stock-fg]] 는 규칙 통과·계좌 기각,
[[us-drop-n1-reject]] 는 규칙 꼴찌·계좌 필수). 그래서 마지막으로 계좌에 물어본다.

물음은 하나다 — **다중검정 기각을 잠시 접어 두면, 이 규칙이 계좌를 낫게 하는가?**
계좌가 뚜렷이 좋아지지 않으면 두 관문을 다 못 넘은 것이니 깨끗하게 끝난다.

후보(전부 5주↑ 연속 상승 → 2주 눌림 · 눌림 깊이 -8% 이내):
  A 시총 하위50%            월 3.5건 · 중앙 +2.64 · 절삭 +0.82 · 상위5%기여 76%
  B 시총 하위50% + 상승 7주↑  월 1.0건 · 중앙 +3.57 · 절삭 +1.95 · 상위5%기여 51% · 10/11해
  C 시총 하위50% · 60일      월 3.4건 · 중앙 +3.08 · 절삭 +1.09
  D 조건 없음(기준선)         월 19.1건 · 절삭 0.00 · 상위5%기여 **100%**(복권형)

    python week_pullback_acct.py
"""
import glob, pickle, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path
from verdict import block_paths

BASE = Path(__file__).parent
NS = 200
W = 120
SINCE = "20160101"
NM = {"N1": "상승장 신고가", "N2": "낙폭과대", "N3": "저PBR 낙폭", "N4": "자사주 낙폭",
      "N5": "잔잔한 급등주", "N6": "실적 서프라이즈", "N7": "주봉 눌림목"}
t0 = time.time()


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def sec(t):
    print("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


log("미장 패널 · 주봉 재료 만드는 중")
U = pd.read_pickle(BASE / "data/us_scan.pkl")
U = U[((~U.pref.fillna(False)) & (U.rawclose >= 3)).fillna(False)]
U = U.sort_values(["ticker", "date"]).reset_index(drop=True)
U["amt_q"] = U.groupby("date").amt20.rank(pct=True)
U["mq"] = U.groupby(U.date.str[:6]).marcap.rank(pct=True)

dt = pd.to_datetime(U.date, format="%Y%m%d")
Uw = U.assign(_wk=(dt - pd.to_timedelta(dt.dt.dayofweek, unit="D")).dt.strftime("%Y%m%d"))
Wk = (Uw.groupby(["ticker", "_wk"], sort=True)
        .agg(date=("date", "last"), close=("close", "last")).reset_index())
Wk = Wk.sort_values(["ticker", "_wk"]).reset_index(drop=True)
g = Wk.groupby("ticker", sort=False)
wdt = pd.to_datetime(Wk._wk, format="%Y%m%d")
cont = (wdt - wdt.groupby(Wk.ticker).shift(1)).dt.days.eq(7).fillna(False)
wret = (Wk.close / g.close.shift(1) - 1) * 100
upw = ((wret > 0) & cont).fillna(False)
dnw = ((wret < 0) & cont).fillna(False)
Wk["up_n"] = upw.astype(int).groupby([Wk.ticker, (~upw).groupby(Wk.ticker).cumsum()]).cumsum()
Wk["dn_n"] = dnw.astype(int).groupby([Wk.ticker, (~dnw).groupby(Wk.ticker).cumsum()]).cumsum()
Wk["back"] = (Wk.close / Wk.close.where(~dnw).groupby(Wk.ticker).ffill() - 1) * 100
gw = Wk.groupby("ticker", sort=False)
okm = (Wk.dn_n >= 2) & (gw.up_n.shift(2) >= 5)
SIG = pd.DataFrame({"ticker": Wk.ticker, "date": Wk.date,
                    "up_n": gw.up_n.shift(2), "back": Wk.back})[okm.fillna(False)]
SIG = SIG[SIG.back > -8]
del Uw, Wk

# ── N6 (실적 서프라이즈) — 사이트 정의 그대로 ─────────────────────────────
E = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(str(BASE / "data/us/analyst/*.pkl")))],
              ignore_index=True)
E["dt"] = pd.to_datetime(E["Earnings Date"], utc=True, errors="coerce")
E = E.dropna(subset=["dt", "Surprise(%)"]).copy()
E["edate"] = E.dt.dt.tz_convert("US/Eastern").dt.strftime("%Y%m%d")
E = E.drop_duplicates(["ticker", "edate"], keep="last")
cal = np.array(sorted(U.date.unique()))
DD = {d: i for i, d in enumerate(cal)}
E["bdate"] = [cal[i] if i < len(cal) else None
              for i in np.searchsorted(cal, E.edate.values, "right")]
E = E.dropna(subset=["bdate"])
E["sur"] = E["Surprise(%)"].astype(float)
E["q"] = E.groupby("bdate").sur.rank(pct=True)
E = E[E.groupby("bdate").sur.transform("size") >= 5]
U["_k"] = U.ticker + U.date
U["peadq"] = U._k.map(dict(zip(E.ticker + E.bdate, E.q)))
U["ret1"] = (U.close / U.groupby("ticker", sort=False).close.shift(1) - 1) * 100


def dedup(X, h):
    X = X[(X.buy > 0) & (X.date >= SINCE)].dropna(subset=["n%d" % h]).sort_values("date")
    keep, last = [], {}
    for t, d_, ix in zip(X.ticker.values, X.date.values, X.index):
        i = DD[d_]
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h
        keep.append(ix)
    Y = X.loc[keep]
    return pd.DataFrame({"date": Y.date.values, "ticker": Y.ticker.values,
                         "ret": Y["n%d" % h].astype(float).values, "amt20": Y.amt20.values})


PE = dedup(U[((U.amt_q >= 0.6) & (U.peadq >= 0.7) & (U.ret1 >= 3)).fillna(False)], 60)

with open(BASE / "data" / "sector_drop_us_sig.pkl", "rb") as f:
    C = pickle.load(f)
S5, DS, ADI, PCT5 = C["S"], C["DS"], C["ADI"], C["PCT"]
DSS = set(DS)
PE = PE[PE.date.isin(DSS)].reset_index(drop=True)
S6 = pd.concat([S5, pd.DataFrame({"date": PE.date.values, "ticker": PE.ticker.values,
                                  "di": [ADI[d] for d in PE.date.values], "rid": "N6",
                                  "pct": 5, "mx": 3, "hold": 60, "ret": PE.ret.values,
                                  "amt20": PE.amt20.values})],
               ignore_index=True).sort_values("di").reset_index(drop=True)
PCT6 = dict(PCT5)
PCT6["N6"] = 5
NMON = len(set(d[:6] for d in DS))

KEYU = U.ticker + U.date


def n7(cond_sig, extra=None, hold=40, pct=5, mx=3):
    """주봉 눌림목 신호를 계좌가 쓰는 꼴로 만든다."""
    z = SIG if cond_sig is None else SIG[cond_sig]
    m = KEYU.isin(set(z.ticker + z.date)) & (U.amt_q >= 0.60).fillna(False)
    if extra is not None:
        m = m & extra.fillna(False)
    Y = dedup(U[m], hold)
    Y = Y[Y.date.isin(DSS)]
    return pd.DataFrame({"date": Y.date.values, "ticker": Y.ticker.values,
                         "di": [ADI[d] for d in Y.date.values], "rid": "N7",
                         "pct": pct, "mx": mx, "hold": hold, "ret": Y.ret.values,
                         "amt20": Y.amt20.values})


def sim(S, PCT, seed=None, cash_cap=1.0, curve=False):
    rng = np.random.default_rng(seed) if seed is not None else None
    nav, held, cnt = 1.0, {}, {}
    byd = {d: gg for d, gg in S[S.date.isin(DSS)].groupby("date")}
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
            lg.append((r.rid, d, r.ret, r.pct / 100))
    for v in held.values():
        nav *= 1 + v[1] / 100
    return dict(nav=nav, mdd=mdd * 100, expo=float(np.mean(inv)),
                L=pd.DataFrame(lg, columns=["rid", "date", "ret", "amt"]),
                cv=pd.DataFrame(cv, columns=["date", "nav"]) if curve else None)


SMALL = (U.mq <= 0.50)
CFG = [("지금 (6규칙)", None),
       ("A 시총하위50% (5/3·40일)", n7(SIG.index.isin(SIG.index), SMALL, 40, 5, 3)),
       ("B A + 상승 7주↑ (5/3·40일)", n7(SIG.up_n >= 7, SMALL, 40, 5, 3)),
       ("C 시총하위50% · 60일", n7(SIG.index.isin(SIG.index), SMALL, 60, 5, 3)),
       ("D 조건 없음 (5/3·40일)", n7(None, None, 40, 5, 3)),
       ("B 비중 8 · 자리 4", n7(SIG.up_n >= 7, SMALL, 40, 8, 4))]
log("  후보 신호 수: " + " · ".join("%s %s건" % (l[:1], f"{len(s):,}")
                                 for l, s in CFG[1:] if s is not None))

sec("① 계좌 — 새 규칙을 얹으면 (%d시드 짝비교)" % NS)
b = [sim(S6, PCT6, seed=k) for k in range(NS)]
BN = np.array([x["nav"] for x in b])
BM = np.array([x["mdd"] for x in b])
log("  기준선 끝")
print("  %-26s%8s%7s%9s%9s%11s%10s%9s"
      % ("구성", "월 후보", "노출", "자산", "낙폭", "시드중앙", "자산승", "낙폭승"))
OUT = {}
for lbl, add in CFG:
    if add is None:
        S, P = S6, PCT6
    else:
        S = pd.concat([S6, add], ignore_index=True).sort_values("di").reset_index(drop=True)
        P = dict(PCT6); P["N7"] = float(add.pct.iloc[0])
    a = sim(S, P)
    rr = [sim(S, P, seed=k) for k in range(NS)]
    n = np.array([x["nav"] for x in rr])
    m = np.array([x["mdd"] for x in rr])
    OUT[lbl] = (S, P, a, n, m)
    per = "—" if add is None else "%.1f건" % (len(add) / NMON)
    if add is None:
        print("  %-26s%8s%6.0f%%%8.2f배%8.1f%%%10.2f배%10s%9s"
              % (lbl, per, a["expo"] * 100, a["nav"], a["mdd"], np.median(n), "—", "—"))
    else:
        print("  %-26s%8s%6.0f%%%8.2f배%8.1f%%%10.2f배%7d/%d%6d/%d"
              % (lbl, per, a["expo"] * 100, a["nav"], a["mdd"], np.median(n),
                 (n > BN).sum(), NS, (m > BM).sum(), NS))
    log("  %s 끝" % lbl)
print("\n  ※ %d/%d 이 동전이다. 120/200(60%%) 은 넘어야 채택을 말할 수 있다." % (NS // 2, NS))

sec("② 경로분포")
print("  %-26s%10s%10s%9s%9s%14s%11s"
      % ("", "실제낙폭", "낙폭중앙", "하위5%", "하위1%", "언더워터 하위5%", "자산하위5%"))
for lbl in OUT:
    S, P, _, _, _ = OUT[lbl]
    a = sim(S, P, curve=True)
    mm = a["cv"].assign(ym=a["cv"].date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100
    Pt = block_paths(mm, n_paths=5000, mean_block=3)
    print("  %-26s%9.1f%%%9.1f%%%8.1f%%%8.1f%%%12.1f년%10.2f배"
          % (lbl, a["mdd"], Pt.mdd.median(), np.percentile(Pt.mdd, 5),
             np.percentile(Pt.mdd, 1), np.percentile(Pt.under, 95) / 12,
             np.percentile(Pt.nav, 5)))

sec("③ 규칙별 체결 — 새 규칙이 누구 자리를 뺏나")
for lbl in ("지금 (6규칙)", "B A + 상승 7주↑ (5/3·40일)", "D 조건 없음 (5/3·40일)"):
    if lbl not in OUT:
        continue
    S, P, a, _, _ = OUT[lbl]
    L = a["L"]
    print("\n  [%s]  노출 %.0f%%" % (lbl, a["expo"] * 100))
    print("    %-16s%8s%9s%8s%11s%11s" % ("규칙", "체결", "평균%", "승률", "기여%p", "월 체결"))
    for r in ["N1", "N2", "N3", "N4", "N5", "N6", "N7"]:
        z = L[L.rid == r]
        if not len(z):
            continue
        print("    %-16s%8s%+9.2f%7.0f%%%+11.1f%10.1f건"
              % (NM[r], f"{len(z):,}", z.ret.mean(), (z.ret > 0).mean() * 100,
                 (z.amt * z.ret / 100).sum() * 100, len(z) / NMON))
print("\n총 %.0f초" % (time.time() - t0))
