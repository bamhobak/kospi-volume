# -*- coding: utf-8 -*-
"""**채택 판정 — 마지막 두 관문** (2026-09-15).

내부자·PEAD 둘 다 계좌로는 강하다. 그런데 아직 안 잰 게 둘 있다.

  ① **연도별 — 특히 최근 해.** 이 집안은 '최근 해 성적' 을 필수 기준으로 쓴다
     ([[bull-axis-n1]] 에서 2026 진입분 -5% 로 기각한 전례). 내부자는 2026 중앙 -4.5% 인데
     PEAD 는 아직 안 봤다.
  ② **둘을 동시에 얹으면.** 각각만 재 봤다. 둘 다 넣으면 서로 자리를 빼앗아 합이 안 될 수 있다.

덤으로 PEAD 의 복권형 점검(상위 5% 기여)과 겹침도 여기서 낸다.

    python us_adopt.py
"""
import glob, pickle, sys, warnings
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
      "N5": "잔잔한 급등주", "PE": "실적 서프라이즈", "IN": "내부자 매수"}


def sec(t):
    print("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


# ── PEAD 신호 ────────────────────────────────────────────────────────────
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


PE3 = sigs(uni & (A.peadq >= 0.7) & (A.ret1 >= 3), 60)
PE5 = sigs(uni & (A.peadq >= 0.7) & (A.ret1 >= 5), 60)
IN = pd.read_pickle(BASE / "data/ins_signals_tmp.pkl").rename(columns={"r": "ret"})

with open(BASE / "data" / "sector_drop_us_sig.pkl", "rb") as f:
    C = pickle.load(f)
S5, DS, ADI, PCT5 = C["S"], C["DS"], C["ADI"], C["PCT"]
DSS = set(DS)
PE3, PE5, IN = [z[z.date.isin(DSS)].reset_index(drop=True) for z in (PE3, PE5, IN)]

sec("① 연도별 — 최근 해가 필수 기준이다")
print("  %-18s%7s%9s%9s%7s%10s" % ("규칙", "신호", "평균%", "중앙%", "승률", "상위5%기여"))
for lbl, z, in (("실적 서프라이즈 갭+3%", PE3), ("실적 서프라이즈 갭+5%", PE5), ("내부자 매수", IN)):
    v = z.ret.astype(float)
    t5 = v.nlargest(max(1, len(v) // 20)).sum() / v.sum() * 100
    print("  %-18s%7s%+9.2f%+9.2f%6.0f%%%9.0f%%" % (lbl, f"{len(z):,}", v.mean(), v.median(),
                                                    (v > 0).mean() * 100, t5))
    yr = z.assign(y=z.date.str[:4]).groupby("y").ret.agg(["size", "mean", "median"])
    print("     " + "  ".join("%s:%+.1f(%d)" % (i[2:], r["median"], r["size"]) for i, r in yr.iterrows()))
    print("     양수해 %d/%d" % ((yr["median"] > 0).sum(), len(yr)))


def add(S, P, z, rid, pct, mx, hold):
    a = pd.DataFrame({"date": z.date.values, "ticker": z.ticker.values,
                      "di": [ADI[d] for d in z.date.values], "rid": rid,
                      "pct": pct, "mx": mx, "hold": hold, "ret": z.ret.values,
                      "amt20": z.amt20.values})
    P2 = dict(P); P2[rid] = pct
    return pd.concat([S, a], ignore_index=True).sort_values("di").reset_index(drop=True), P2


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


sec("② 계좌 — 하나씩 · 둘 다 · 절반 비중 (%d시드)" % NS)
b100 = [sim(S5, PCT5, DS, seed=k) for k in range(NS)]
BN = [x["nav"] for x in b100]
BM = [x["mdd"] for x in b100]
b = sim(S5, PCT5, DS)
CFG = [("5규칙 (지금)", None)]
S_pe3, P_pe3 = add(S5, PCT5, PE3, "PE", 5, 3, 60)
S_pe5, P_pe5 = add(S5, PCT5, PE5, "PE", 5, 3, 60)
S_in, P_in = add(S5, PCT5, IN, "IN", 5, 3, 40)
S_b, P_b = add(*add(S5, PCT5, PE3, "PE", 5, 3, 60), IN, "IN", 5, 3, 40)
S_bh, P_bh = add(*add(S5, PCT5, PE3, "PE", 3, 3, 60), IN, "IN", 3, 3, 40)
CFG += [("+PEAD(갭+3%)", (S_pe3, P_pe3)), ("+PEAD(갭+5%)", (S_pe5, P_pe5)),
        ("+내부자", (S_in, P_in)), ("+둘 다 (비중5)", (S_b, P_b)),
        ("+둘 다 (비중3)", (S_bh, P_bh))]
print("  %-20s%7s%9s%9s%12s%9s%9s" % ("구성", "노출", "자산", "낙폭", "시드중앙", "자산승", "낙폭승"))
OUT = {}
for lbl, sp in CFG:
    S, P = (S5, PCT5) if sp is None else sp
    a = sim(S, P, DS)
    rr = [sim(S, P, DS, seed=k) for k in range(NS)]
    OUT[lbl] = (S, P, a, rr)
    if sp is None:
        print("  %-20s%6.0f%%%8.2f배%8.1f%%%11.2f배%9s%9s"
              % (lbl, a["expo"] * 100, a["nav"], a["mdd"], np.median(BN), "—", "—"))
        continue
    wn = sum(1 for x, y in zip(rr, b100) if x["nav"] > y["nav"])
    wm = sum(1 for x, y in zip(rr, b100) if x["mdd"] > y["mdd"])
    print("  %-20s%6.0f%%%8.2f배%8.1f%%%11.2f배%7d/%d%7d/%d"
          % (lbl, a["expo"] * 100, a["nav"], a["mdd"],
             np.median([x["nav"] for x in rr]), wn, NS, wm, NS))

sec("③ 경로분포 — 꼬리와 언더워터")
print("  %-20s%11s%10s%9s%9s%14s%11s"
      % ("", "실제낙폭", "낙폭중앙", "하위5%", "하위1%", "언더워터 하위5%", "자산하위5%"))
for lbl in ("5규칙 (지금)", "+PEAD(갭+3%)", "+내부자", "+둘 다 (비중5)", "+둘 다 (비중3)"):
    S, P, _, _ = OUT[lbl]
    a = sim(S, P, DS, curve=True)
    m = a["cv"].assign(ym=a["cv"].date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100
    Pt = block_paths(m, n_paths=5000, mean_block=3)
    print("  %-20s%10.1f%%%9.1f%%%8.1f%%%8.1f%%%12.1f년%10.2f배"
          % (lbl, a["mdd"], Pt.mdd.median(), np.percentile(Pt.mdd, 5), np.percentile(Pt.mdd, 1),
             np.percentile(Pt.under, 95) / 12, np.percentile(Pt.nav, 5)))

sec("④ 둘 다 넣었을 때 규칙별 — 서로 자리를 뺏나")
for lbl in ("+PEAD(갭+3%)", "+내부자", "+둘 다 (비중5)"):
    L = OUT[lbl][2]["L"]
    print("\n  [%s]" % lbl)
    print("    %-16s%7s%9s%7s%10s" % ("규칙", "체결", "평균%", "승률", "기여%p"))
    for r in ["N1", "N2", "N3", "N4", "N5", "PE", "IN"]:
        z = L[L.rid == r]
        if not len(z):
            continue
        print("    %-16s%7s%+9.2f%7.0f%%%+10.1f"
              % (NM[r], f"{len(z):,}", z.ret.mean(), (z.ret > 0).mean() * 100,
                 (z.amt * z.ret / 100).sum() * 100))

sec("⑤ 겹침 — PEAD 가 기존 규칙과 얼마나 겹치나")
S, _, _, _ = OUT["+PEAD(갭+3%)"]
oi = S[S.rid == "PE"]
oo = S[S.rid != "PE"]
key = {}
for t, di in zip(oo.ticker.values, oo.di.values):
    key.setdefault(t, []).append(di)
near = sum(1 for t, di in zip(oi.ticker.values, oi.di.values)
           if any(abs(di - x) <= 5 for x in key.get(t, [])))
print("  PEAD 신호 %s건 중 기존 규칙과 같은 종목 ±5일 겹침 %s건 (%.0f%%)"
      % (f"{len(oi):,}", f"{near:,}", near / max(len(oi), 1) * 100))
