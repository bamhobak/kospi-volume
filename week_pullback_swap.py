# -*- coding: utf-8 -*-
"""**주봉 눌림목을 기존 상승장 규칙과 바꿔치면?** (2026-09-16 물음).

"다른 상승장 규칙에 비해 메리트가 없어? 있으면 교체하면 되잖아."

맞는 물음이다. 앞(`week_pullback_acct.py`)에서는 **얹기만** 재 봤고 전부 기각이었는데,
기각 이유가 "노출이 78 → 85% 로 올라 [낙폭과대]가 폭락 바닥에서 살 현금을 먹었다" 였다.
**바꿔치면 그 이유가 사라진다** — 자리도 비중도 그대로이니 노출이 안 늘어난다.

거래별로만 보면 새 규칙이 [상승장 신고가]보다 확실히 낫다.

  | | 중앙 | 절삭 | 상위5%기여 | 승률 |
  |---|---|---|---|---|
  | [상승장 신고가] | +1.44 | **-0.39** | **126%**(복권형) | 56% |
  | [잔잔한 급등주] | +2.22 | +1.05 | 65% | 57% |
  | 주봉 눌림목(시총하위50%+7주↑) | **+3.57** | **+1.95** | **51%** | **66%** |

그런데 [[us-drop-n1-reject]] 에서 봤듯 **[상승장 신고가]는 계좌가 실제로 사는 225건만 보면
평균 +3.23% 로 2위**다. 자리 경쟁(거래대금 큰 순)이 이미 좋은 쪽을 골라내고 있어서
규칙 전체의 분포로 우열을 매기면 안 된다. 그러니 계좌에 직접 물어본다.

⚠ 바꿔치기는 **후보 수가 맞아야** 말이 된다. [상승장 신고가]는 월 75건인데 조인 눌림목은
   월 2건이라 그 자리에 넣으면 자리가 텅 빈다. 그래서 자리마다 **건수가 비슷한 판본**을 쓴다.
     [상승장 신고가](월 75) 자리 → 눌림목 D(조건 없음 · 월 38.6)
     [잔잔한 급등주](월 6.4) 자리 → 눌림목 A(시총하위50% · 월 7.1)

  ① 노출을 찍어 가며 바꿔치기 (200시드)
  ② 경로분포
  ③ 규칙별 체결 — [낙폭과대]가 살아 있나

    python week_pullback_swap.py
"""
import glob, pickle, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path
from verdict import block_paths

BASE = Path(__file__).parent
NS = 200
W = 124
SINCE = "20160101"
NM = {"N1": "상승장 신고가", "N2": "낙폭과대", "N3": "저PBR 낙폭", "N4": "자사주 낙폭",
      "N5": "잔잔한 급등주", "N6": "실적 서프라이즈", "N7": "주봉 눌림목", "N8": "주봉 눌림목2"}
t0 = time.time()


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def sec(t):
    print("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


log("미장 패널 · 주봉 재료")
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
gk = Wk.groupby("ticker", sort=False)
wdt = pd.to_datetime(Wk._wk, format="%Y%m%d")
cont = (wdt - wdt.groupby(Wk.ticker).shift(1)).dt.days.eq(7).fillna(False)
wret = (Wk.close / gk.close.shift(1) - 1) * 100
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

# ── N6 ───────────────────────────────────────────────────────────────────
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


def pull(rid, sel=None, small=False, hold=40, pct=5, mx=3):
    z = SIG if sel is None else SIG[sel]
    m = KEYU.isin(set(z.ticker + z.date)) & (U.amt_q >= 0.60).fillna(False)
    if small:
        m = m & (U.mq <= 0.50).fillna(False)
    Y = dedup(U[m.fillna(False)], hold)
    Y = Y[Y.date.isin(DSS)]
    return pd.DataFrame({"date": Y.date.values, "ticker": Y.ticker.values,
                         "di": [ADI[d] for d in Y.date.values], "rid": rid,
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


# 자리 크기에 맞춘 판본
D_BIG = pull("N7", None, False, 40, 10, 4)          # 조건 없음 · [상승장 신고가] 자리(10/4)
A_BIG = pull("N7", None, True, 40, 10, 4)           # 시총하위50% · 같은 자리
A_SML = pull("N7", None, True, 40, 5, 3)            # 시총하위50% · [잔잔한 급등주] 자리(5/3)
B_SML = pull("N7", SIG.up_n >= 7, True, 40, 5, 3)   # +상승 7주↑ · 같은 자리
log("  월 후보 — D(조건없음) %.1f · A(시총하위50%%) %.1f · B(A+7주↑) %.1f"
    % (len(D_BIG) / NMON, len(A_BIG) / NMON, len(B_SML) / NMON))


def swap(drop, add, pct=None):
    """drop 규칙을 빼고 add 를 넣는다. 자리·비중은 add 쪽 값을 쓴다."""
    z = S6[~S6.rid.isin(drop)] if drop else S6
    z = pd.concat([z] + add, ignore_index=True).sort_values("di").reset_index(drop=True)
    P = {k: v for k, v in PCT6.items() if k not in drop}
    for a in add:
        P[a.rid.iloc[0]] = float(a.pct.iloc[0])
    return z, P


B2 = B_SML.copy(); B2["rid"] = "N8"
A2 = A_SML.copy(); A2["rid"] = "N8"
CFG = [
    ("지금 (6규칙)", None, []),
    ("[상승장 신고가] → 눌림목D", ["N1"], [D_BIG]),
    ("[상승장 신고가] → 눌림목A", ["N1"], [A_BIG]),
    ("[잔잔한 급등주] → 눌림목A", ["N5"], [A_SML]),
    ("[잔잔한 급등주] → 눌림목B", ["N5"], [B_SML]),
    ("둘 다 → D + B", ["N1", "N5"], [D_BIG, B2]),
    ("둘 다 → A + B", ["N1", "N5"], [A_BIG, B2]),
]

sec("① 바꿔치기 — 노출이 그대로인가부터 본다 (%d시드)" % NS)
b = [sim(S6, PCT6, seed=k) for k in range(NS)]
BN = np.array([x["nav"] for x in b])
BM = np.array([x["mdd"] for x in b])
log("  기준선 끝")
print("  %-28s%7s%9s%9s%11s%10s%9s"
      % ("구성", "노출", "자산", "낙폭", "시드중앙", "자산승", "낙폭승"))
OUT = {}
for lbl, drop, add in CFG:
    S, P = (S6, PCT6) if drop is None else swap(drop, add)
    a = sim(S, P)
    rr = [sim(S, P, seed=k) for k in range(NS)]
    n = np.array([x["nav"] for x in rr])
    m = np.array([x["mdd"] for x in rr])
    OUT[lbl] = (S, P, a, n, m)
    if drop is None:
        print("  %-28s%6.0f%%%8.2f배%8.1f%%%10.2f배%10s%9s"
              % (lbl, a["expo"] * 100, a["nav"], a["mdd"], np.median(n), "—", "—"))
    else:
        print("  %-28s%6.0f%%%8.2f배%8.1f%%%10.2f배%7d/%d%6d/%d"
              % (lbl, a["expo"] * 100, a["nav"], a["mdd"], np.median(n),
                 (n > BN).sum(), NS, (m > BM).sum(), NS))
    log("  %s 끝" % lbl)
print("\n  ※ %d/%d 이 동전이다." % (NS // 2, NS))

sec("② 경로분포")
print("  %-28s%10s%10s%9s%9s%14s%11s"
      % ("", "실제낙폭", "낙폭중앙", "하위5%", "하위1%", "언더워터 하위5%", "자산하위5%"))
for lbl in OUT:
    S, P, _, _, _ = OUT[lbl]
    a = sim(S, P, curve=True)
    mm = a["cv"].assign(ym=a["cv"].date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100
    Pt = block_paths(mm, n_paths=5000, mean_block=3)
    print("  %-28s%9.1f%%%9.1f%%%8.1f%%%8.1f%%%12.1f년%10.2f배"
          % (lbl, a["mdd"], Pt.mdd.median(), np.percentile(Pt.mdd, 5),
             np.percentile(Pt.mdd, 1), np.percentile(Pt.under, 95) / 12,
             np.percentile(Pt.nav, 5)))

sec("③ 규칙별 체결 — [낙폭과대]가 살아 있나 (여기가 핵심이다)")
for lbl in OUT:
    S, P, a, _, _ = OUT[lbl]
    L = a["L"]
    print("\n  [%s]  노출 %.0f%%" % (lbl, a["expo"] * 100))
    print("    %-16s%8s%9s%8s%11s%11s" % ("규칙", "체결", "평균%", "승률", "기여%p", "월 체결"))
    for r in ["N1", "N2", "N3", "N4", "N5", "N6", "N7", "N8"]:
        z = L[L.rid == r]
        if not len(z):
            continue
        print("    %-16s%8s%+9.2f%7.0f%%%+11.1f%10.1f건"
              % (NM[r], f"{len(z):,}", z.ret.mean(), (z.ret > 0).mean() * 100,
                 (z.amt * z.ret / 100).sum() * 100, len(z) / NMON))
print("\n총 %.0f초" % (time.time() - t0))
