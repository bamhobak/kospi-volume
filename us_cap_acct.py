# -*- coding: utf-8 -*-
"""**시총 축 — 계좌 판정** (us_cap_axis.py 후속, 2026-09-15).

십분위 훑기에서 6규칙 중 넷은 축이 아예 없었다(상관 r 이 -0.19 ~ +0.33).
남은 둘만 계좌로 올린다.

  · [저PBR 낙폭]  r=+0.44 · 십분위가 꽤 매끈하게 우상향 · 큰쪽30% 절삭 2.56 (전체 1.70)
  · [자사주 낙폭]  r=+0.40 인데 십분위가 6.2→3.1→5.4→9.1→3.0→11.8 로 **춤을 춘다**
    — 상관만 보면 축 같지만 단조가 아니다. 진짜인지 계좌가 답한다.

⚠ 규칙 단위에서 좋아 보여도 계좌에선 자주 뒤집힌다([[stock-fg]] 전례).
   조이면 신호가 줄어 **노출이 떨어지고**, 그 손해가 종목 질 향상보다 클 때가 많다.
   그래서 노출을 같이 찍고, 200시드 짝비교로 판정한다.

    python us_cap_acct.py
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
      "N5": "잔잔한 급등주", "N6": "실적 서프라이즈"}
t0 = time.time()


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def sec(t):
    print("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


log("시총 순위 붙이는 중")
A = pd.read_pickle(BASE / "data/us_scan.pkl")
M = A[["ticker", "date", "marcap"]].dropna(subset=["marcap"]).copy()
M["mq"] = M.groupby(M.date.str[:6]).marcap.rank(pct=True)
MQ = dict(zip(M.ticker + M.date, M.mq))
del M

# ── N6 신호 (사이트 정의 그대로) ──────────────────────────────────────────
E = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(str(BASE / "data/us/analyst/*.pkl")))],
              ignore_index=True)
E["dt"] = pd.to_datetime(E["Earnings Date"], utc=True, errors="coerce")
E = E.dropna(subset=["dt", "Surprise(%)"]).copy()
E["edate"] = E.dt.dt.tz_convert("US/Eastern").dt.strftime("%Y%m%d")
E = E.drop_duplicates(["ticker", "edate"], keep="last")
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
S6["mq"] = (S6.ticker + S6.date).map(MQ)
PCT6 = dict(PCT5)
PCT6["N6"] = 5
NMON = len(set(d[:6] for d in DS))
log("  신호 %s건 · 시총 붙은 비율 %.0f%%" % (f"{len(S6):,}", S6.mq.notna().mean() * 100))


def variant(cuts=None, pct=None):
    """cuts = {규칙: (하한, 상한)} — 같은 달 시총 순위로 잘라낸다."""
    z = S6
    if cuts:
        m = pd.Series(True, index=z.index)
        for k, (lo, hi) in cuts.items():
            bad = (z.rid == k) & ~((z.mq >= lo) & (z.mq <= hi)).fillna(False)
            m &= ~bad
        z = z[m]
    z = z.copy()
    P = dict(PCT6)
    if pct:
        for k, v in pct.items():
            z.loc[z.rid == k, "pct"] = v
            P[k] = v
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
            lg.append((r.rid, d, r.ret, r.pct / 100))
    for v in held.values():
        nav *= 1 + v[1] / 100
    return dict(nav=nav, mdd=mdd * 100, expo=float(np.mean(inv)),
                L=pd.DataFrame(lg, columns=["rid", "date", "ret", "amt"]),
                cv=pd.DataFrame(cv, columns=["date", "nav"]) if curve else None)


sec("① 계좌 — 시총 조건을 얹으면 (%d시드 짝비교)" % NS)
BS, BP = variant()
b = [sim(BS, BP, seed=k) for k in range(NS)]
BN = np.array([x["nav"] for x in b])
BM = np.array([x["mdd"] for x in b])
log("  기준선 끝")
CFG = [("지금 (조건 없음)", dict()),
       ("저PBR 큰쪽 70%↑", dict(cuts={"N3": (0.30, 1.01)})),
       ("저PBR 큰쪽 50%↑", dict(cuts={"N3": (0.50, 1.01)})),
       ("저PBR 큰쪽 30%만", dict(cuts={"N3": (0.70, 1.01)})),
       ("자사주 큰쪽 50%↑", dict(cuts={"N4": (0.50, 1.01)})),
       ("자사주 큰쪽 30%만", dict(cuts={"N4": (0.70, 1.01)})),
       ("둘 다 큰쪽 50%↑", dict(cuts={"N3": (0.50, 1.01), "N4": (0.50, 1.01)})),
       ("낙폭과대 작은쪽 70%↓", dict(cuts={"N2": (0.0, 0.70)})),
       ("둘 다 50%↑ · 비중↑", dict(cuts={"N3": (0.50, 1.01), "N4": (0.50, 1.01)},
                                pct={"N3": 7, "N4": 7}))]
print("  %-24s%8s%7s%9s%9s%11s%10s%9s"
      % ("구성", "신호", "노출", "자산", "낙폭", "시드중앙", "자산승", "낙폭승"))
OUT = {}
for lbl, kw in CFG:
    S, P = variant(**kw)
    a = sim(S, P)
    rr = [sim(S, P, seed=k) for k in range(NS)]
    n = np.array([x["nav"] for x in rr])
    m = np.array([x["mdd"] for x in rr])
    OUT[lbl] = (S, P, a, n, m)
    if not kw:
        print("  %-24s%8s%6.0f%%%8.2f배%8.1f%%%10.2f배%10s%9s"
              % (lbl, f"{len(S):,}", a["expo"] * 100, a["nav"], a["mdd"], np.median(n), "—", "—"))
    else:
        print("  %-24s%8s%6.0f%%%8.2f배%8.1f%%%10.2f배%7d/%d%6d/%d"
              % (lbl, f"{len(S):,}", a["expo"] * 100, a["nav"], a["mdd"], np.median(n),
                 (n > BN).sum(), NS, (m > BM).sum(), NS))
    log("  %s 끝" % lbl)
print("\n  ※ %d/%d 이 동전이다. 120/200(60%%) 은 넘어야 축이라 부를 수 있다." % (NS // 2, NS))

sec("② 학습·검증 분리 — 과적합인지")
print("  (300시드 쓰기 전에 구간부터 나눠 본다. 오늘 여기서 두 번 데였다)")
print("\n  %-24s%22s%22s" % ("구성", "── 학습 2016~22 ──", "── 검증 2023~26 ──"))
print("  %-24s%11s%11s%11s%11s" % ("", "시드중앙", "자산승", "시드중앙", "자산승"))
SPL = [d for d in DS]
for lbl in ("지금 (조건 없음)", "저PBR 큰쪽 50%↑", "자사주 큰쪽 50%↑", "둘 다 큰쪽 50%↑"):
    S, P, _, _, _ = OUT[lbl]
    row = ""
    for lo, hi in (("2016", "2023"), ("2023", "2030")):
        ds = [d for d in DS if lo <= d < hi]
        g_DS = DS
        globals()["DS"] = ds
        z = [sim(S, P, seed=k)["nav"] for k in range(100)]
        z0 = [sim(BS, BP, seed=k)["nav"] for k in range(100)]
        globals()["DS"] = g_DS
        row += "%10.2f배%8d/100" % (np.median(z), sum(1 for x, y in zip(z, z0) if x > y))
    print("  %-24s%s" % (lbl, row))

sec("③ 경로분포 — 통과한 구성만")
print("  %-24s%10s%10s%9s%9s%14s%11s"
      % ("", "실제낙폭", "낙폭중앙", "하위5%", "하위1%", "언더워터 하위5%", "자산하위5%"))
for lbl in ("지금 (조건 없음)", "저PBR 큰쪽 50%↑", "자사주 큰쪽 50%↑", "둘 다 큰쪽 50%↑"):
    S, P, _, _, _ = OUT[lbl]
    a = sim(S, P, curve=True)
    mm = a["cv"].assign(ym=a["cv"].date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100
    Pt = block_paths(mm, n_paths=5000, mean_block=3)
    print("  %-24s%9.1f%%%9.1f%%%8.1f%%%8.1f%%%12.1f년%10.2f배"
          % (lbl, a["mdd"], Pt.mdd.median(), np.percentile(Pt.mdd, 5),
             np.percentile(Pt.mdd, 1), np.percentile(Pt.under, 95) / 12,
             np.percentile(Pt.nav, 5)))

sec("④ 규칙별 체결 — 조이면 정말 좋은 종목만 남나")
for lbl in ("지금 (조건 없음)", "둘 다 큰쪽 50%↑"):
    S, P, a, _, _ = OUT[lbl]
    L = a["L"]
    print("\n  [%s]  노출 %.0f%%" % (lbl, a["expo"] * 100))
    print("    %-16s%8s%9s%8s%11s%11s" % ("규칙", "체결", "평균%", "승률", "기여%p", "월 체결"))
    for r in ["N1", "N2", "N3", "N4", "N5", "N6"]:
        z = L[L.rid == r]
        if not len(z):
            continue
        print("    %-16s%8s%+9.2f%7.0f%%%+11.1f%10.1f건"
              % (NM[r], f"{len(z):,}", z.ret.mean(), (z.ret > 0).mean() * 100,
                 (z.amt * z.ret / 100).sum() * 100, len(z) / NMON))
print("\n총 %.0f초" % (time.time() - t0))
