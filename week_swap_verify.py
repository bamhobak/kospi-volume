# -*- coding: utf-8 -*-
"""**[잔잔한 급등주] → 주봉 눌림목 교체 — 300시드 재검증** (2026-09-16).

200시드에서 하나가 통과했다.
  [잔잔한 급등주] → 눌림목B(5주↑ 상승·2주 눌림·눌림 -8% 이내·시총하위50%·상승 7주↑)
  자산승 127/200 · 낙폭승 101/200 · 시드중앙 7.37 → 7.95배 · 경로분포 전부 개선

그런데 걸리는 게 둘이다.
  ① 실제 경로(거래대금 순 tie-break)는 9.92 → **6.46배로 떨어진다**. 시드중앙과 방향이 반대다.
     지금 구성의 9.92배가 tie-break 가 준 운이라는 뜻인데([[tiebreak-trail]] 과 같은 구조),
     두 잣대가 갈리면 함부로 못 바꾼다.
  ② 교체인데도 **[낙폭과대]가 무너진다**(평균 +19.98 → +1.07 · 기여 +119.9 → +6.4%p).
     노출은 78% 로 같은데 왜 그런지 봐야 한다.
  ③ 이 규칙은 이미 **다중검정에서 기각**됐다(B 판본 진짜일확률 73.2%).

이 집안은 30시드에 두 번 데였다([[hype-rally]]). **300시드 + 학습·검증 분리**까지 간다.

  ① 300시드 짝비교
  ② 학습 2016~22 / 검증 2023~26 따로
  ③ [낙폭과대]가 무너지는 게 특정 해 한 사건인가 — 연도별 체결 성적
  ④ 연도별 계좌

    python week_swap_verify.py
"""
import glob, pickle, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
NS = 300
W = 118
SINCE = "20160101"
NM = {"N1": "상승장 신고가", "N2": "낙폭과대", "N3": "저PBR 낙폭", "N4": "자사주 낙폭",
      "N5": "잔잔한 급등주", "N6": "실적 서프라이즈", "N7": "주봉 눌림목"}
t0 = time.time()


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def sec(t):
    print("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


log("재료 만드는 중")
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

m7 = (KEYU.isin(set(SIG[SIG.up_n >= 7].ticker + SIG[SIG.up_n >= 7].date))
      & (U.amt_q >= 0.60) & (U.mq <= 0.50)).fillna(False)
Y7 = dedup(U[m7], 40)
Y7 = Y7[Y7.date.isin(DSS)]
N7 = pd.DataFrame({"date": Y7.date.values, "ticker": Y7.ticker.values,
                   "di": [ADI[d] for d in Y7.date.values], "rid": "N7",
                   "pct": 5, "mx": 3, "hold": 40, "ret": Y7.ret.values, "amt20": Y7.amt20.values})
SWAP = pd.concat([S6[S6.rid != "N5"], N7], ignore_index=True).sort_values("di").reset_index(drop=True)
PSWAP = {k: v for k, v in PCT6.items() if k != "N5"}
PSWAP["N7"] = 5
log("  눌림목B %s건 (월 %.1f) · [잔잔한 급등주] %s건"
    % (f"{len(N7):,}", len(N7) / NMON, f"{int((S6.rid == 'N5').sum()):,}"))


def sim(S, PCT, seed=None, days=None, cash_cap=1.0):
    ds = days or DS
    dss = set(ds)
    rng = np.random.default_rng(seed) if seed is not None else None
    nav, held, cnt = 1.0, {}, {}
    byd = {d: gg for d, gg in S[S.date.isin(dss)].groupby("date")}
    peak, mdd, inv, lg = 1.0, 0.0, [], []
    for d in ds:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            nav *= 1 + held.pop(k)[1] / 100
            cnt[k[0]] = cnt.get(k[0], 0) - 1
        peak = max(peak, nav)
        mdd = min(mdd, nav / peak - 1)
        inv.append(sum(PCT[k[0]] for k in held) / 100)
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
                L=pd.DataFrame(lg, columns=["rid", "date", "ret", "amt"]))


sec("① 300시드 짝비교 — 200시드에서 127/200(63.5%) 이었다")
A = [sim(S6, PCT6, seed=k) for k in range(NS)]
B = [sim(SWAP, PSWAP, seed=k) for k in range(NS)]
an = np.array([x["nav"] for x in A]); bn = np.array([x["nav"] for x in B])
am = np.array([x["mdd"] for x in A]); bm = np.array([x["mdd"] for x in B])
print("  %-22s%11s%11s%11s%11s" % ("", "시드중앙", "시드평균", "최악", "최고"))
print("  %-22s%10.2f배%10.2f배%10.2f배%10.2f배"
      % ("지금 (6규칙)", np.median(an), an.mean(), an.min(), an.max()))
print("  %-22s%10.2f배%10.2f배%10.2f배%10.2f배"
      % ("[잔잔한]→눌림목B", np.median(bn), bn.mean(), bn.min(), bn.max()))
print("\n  자산승 %d/%d (%.0f%%) · 낙폭승 %d/%d (%.0f%%)"
      % ((bn > an).sum(), NS, (bn > an).mean() * 100, (bm > am).sum(), NS, (bm > am).mean() * 100))
print("  차이 중앙 %+.2f배 · 평균 %+.2f배" % (np.median(bn - an), (bn - an).mean()))

sec("② 학습 2016~22 / 검증 2023~26 따로 (각 100시드)")
print("  %-22s%12s%12s%12s%12s" % ("", "학습 지금", "학습 교체", "검증 지금", "검증 교체"))
row = []
for lo, hi in (("2016", "2023"), ("2023", "2030")):
    ds = [d for d in DS if lo <= d < hi]
    a = [sim(S6, PCT6, seed=k, days=ds)["nav"] for k in range(100)]
    b = [sim(SWAP, PSWAP, seed=k, days=ds)["nav"] for k in range(100)]
    row.append((np.median(a), np.median(b), sum(1 for x, y in zip(b, a) if x > y)))
print("  %-22s%11.2f배%11.2f배%11.2f배%11.2f배"
      % ("시드중앙", row[0][0], row[0][1], row[1][0], row[1][1]))
print("  %-22s%12s%12s%12s%12s"
      % ("자산승", "—", "%d/100" % row[0][2], "—", "%d/100" % row[1][2]))

sec("③ [낙폭과대]가 무너지는 게 한 사건인가 — 연도별 체결 평균 (거래대금 순 경로)")
la = sim(S6, PCT6)["L"]
lb = sim(SWAP, PSWAP)["L"]
print("  %-14s" % "구성" + "".join("%9s" % y for y in range(2016, 2027)))
for lbl, L in (("지금", la), ("교체", lb)):
    z = L[L.rid == "N2"].copy()
    z["y"] = z.date.str[:4]
    g = z.groupby("y").ret.mean()
    c = z.groupby("y").size()
    print("  %-14s" % lbl + "".join(("%8.1f" % g[str(y)]) if str(y) in g.index else "%9s" % "—"
                                    for y in range(2016, 2027)))
    print("  %-14s" % "  (건수)" + "".join(("%8d" % c[str(y)]) if str(y) in c.index else "%9s" % "—"
                                          for y in range(2016, 2027)))

sec("④ [낙폭과대] 성적을 300시드로 — 한 경로 얘기가 아닌지")
for lbl, S, P in (("지금", S6, PCT6), ("교체", SWAP, PSWAP)):
    v = []
    for k in range(60):
        L = sim(S, P, seed=k)["L"]
        z = L[L.rid == "N2"].ret
        if len(z):
            v.append(z.mean())
    print("  %-14s[낙폭과대] 체결 평균 — 시드중앙 %+.2f%% · 하위10%% %+.2f%% · 상위10%% %+.2f%%"
          % (lbl, np.median(v), np.percentile(v, 10), np.percentile(v, 90)))

sec("⑤ 연도별 계좌 (거래대금 순 경로)")
print("  %-14s" % "구성" + "".join("%9s" % y for y in range(2016, 2027)))
for lbl, S, P in (("지금", S6, PCT6), ("교체", SWAP, PSWAP)):
    row2 = ""
    for y in range(2016, 2027):
        ds = [d for d in DS if d.startswith(str(y))]
        if not ds:
            row2 += "%9s" % "—"; continue
        row2 += "%8.0f%%" % ((sim(S, P, days=ds)["nav"] - 1) * 100)
    print("  %-14s%s" % (lbl, row2))
print("\n총 %.0f초" % (time.time() - t0))
