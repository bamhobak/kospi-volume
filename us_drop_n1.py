# -*- coding: utf-8 -*-
"""**[상승장 신고가]를 빼면?** (2026-09-15 물음).

"실적 서프라이즈가 상승장 신고가보다 수익률이 좋으니깐 상승장 신고가를 없앨까?"

⚠ 이 집안엔 전례가 있다([[contrib-not-removal]]).
   국내 [업종붕괴 이탈]은 거래별 성적이 제일 나빴는데, 빼니까 계좌가 21.65 → **19.21배**로
   **떨어졌다**. 거래별 평균과 계좌 기여는 다른 물건이다. 이유는 셋이다.
     · 신호가 많은 규칙은 **다른 규칙이 쉴 때 노출을 채운다**(빈 자리를 메운다).
     · 낮은 상관은 그 자체로 값이 있다 — 평균이 낮아도 **낙폭을 눌러준다**.
     · 자리를 비워도 **다른 규칙이 그만큼 더 사주지 않는다**(후보가 없다).
   그러니 거래별 수익률이 아니라 **계좌로** 판정한다. 200시드.

  ① 거래별 성적 — 정말 N6가 N1보다 나은가 (같은 잣대로)
  ② 계좌 — 빼기 / 비중 줄이기 / 자리 줄이기 / 뺀 몫을 N6에 주기
  ③ 경로분포 — 낙폭 꼬리와 언더워터
  ④ 노출 — N1을 빼면 그 자리를 누가 메우나
  ⑤ 연도별 — N1이 짐이 된 해가 따로 있나

    python us_drop_n1.py
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


# ── N6(실적 서프라이즈) 신호를 사이트 정의 그대로 만든다 ──────────────────
log("N6 신호 만드는 중")
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
cond = ((A.amt_q >= 0.6) & (A.peadq >= 0.7) & (A.ret1 >= 3)).fillna(False)
X = A[cond].dropna(subset=["n60"])
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
PCT6 = dict(PCT5)
PCT6["N6"] = 5
NMON = len(set(d[:6] for d in DS))
log("  N1 %s건 · N6 %s건 · %d개월" % (f"{(S6.rid == 'N1').sum():,}", f"{len(PE):,}", NMON))


def variant(pct=None, mx=None, drop=None):
    """비중·자리를 갈아 끼운 판을 만든다."""
    z = S6[S6.rid != drop].copy() if drop else S6.copy()
    P = {k: v for k, v in PCT6.items() if k != drop}
    if pct:
        for k, v in pct.items():
            z.loc[z.rid == k, "pct"] = v
            P[k] = v
    if mx:
        for k, v in mx.items():
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
            lg.append((r.rid, d, r.ret, r.pct / 100))
    for v in held.values():
        nav *= 1 + v[1] / 100
    return dict(nav=nav, mdd=mdd * 100, expo=float(np.mean(inv)),
                L=pd.DataFrame(lg, columns=["rid", "date", "ret", "amt"]),
                cv=pd.DataFrame(cv, columns=["date", "nav"]) if curve else None)


sec("① 거래별 성적 — 정말 N6가 N1보다 나은가 (같은 잣대 · 전량 동일금액 가정)")
print("  %-16s%8s%9s%9s%8s%9s%11s%10s"
      % ("규칙", "신호", "평균%", "중앙%", "승률", "절삭평균", "상위5%기여", "최악"))
for r in ["N1", "N2", "N3", "N4", "N5", "N6"]:
    v = S6[S6.rid == r].ret.astype(float)
    tr = v[v <= v.quantile(0.95)].mean()
    t5 = v.nlargest(max(1, len(v) // 20)).sum() / v.sum() * 100
    print("  %-16s%8s%+9.2f%+9.2f%7.0f%%%+9.2f%10.0f%%%+10.1f"
          % (NM[r], f"{len(v):,}", v.mean(), v.median(), (v > 0).mean() * 100, tr, t5, v.min()))
print("\n  ※ '절삭평균'은 위쪽 5%%를 잘라낸 평균이다. 상위5%% 기여가 100%%를 넘으면")
print("    나머지 95%%가 합쳐서 마이너스라는 뜻 — 복권형이다.")

sec("② 계좌 — %d시드 짝비교" % NS)
BASE_S, BASE_P = variant()
b200 = [sim(BASE_S, BASE_P, seed=k) for k in range(NS)]
BN = np.array([x["nav"] for x in b200])
BM = np.array([x["mdd"] for x in b200])
log("  기준선 끝")
CFG = [("지금 (6규칙)", dict()),
       ("N1 빼기", dict(drop="N1")),
       ("N1 빼고 N6 10/자리4", dict(drop="N1", pct={"N6": 10}, mx={"N6": 4})),
       ("N1 빼고 나머지 비중↑", dict(drop="N1", pct={"N2": 7, "N3": 7, "N4": 7, "N5": 7, "N6": 8})),
       ("N1 비중 10→5", dict(pct={"N1": 5})),
       ("N1 자리 4→2", dict(mx={"N1": 2})),
       ("N1 자리 4→2 · N6 10", dict(mx={"N1": 2}, pct={"N6": 10})),
       ("N6 비중 5→10", dict(pct={"N6": 10}))]
print("  %-24s%7s%9s%9s%11s%10s%10s%9s"
      % ("구성", "노출", "자산", "낙폭", "시드중앙", "시드최악", "자산승", "낙폭승"))
OUT = {}
for lbl, kw in CFG:
    S, P = variant(**kw)
    a = sim(S, P)
    rr = [sim(S, P, seed=k) for k in range(NS)]
    n = np.array([x["nav"] for x in rr])
    m = np.array([x["mdd"] for x in rr])
    OUT[lbl] = (S, P, a, n, m)
    if not kw:
        print("  %-24s%6.0f%%%8.2f배%8.1f%%%10.2f배%9.2f배%10s%9s"
              % (lbl, a["expo"] * 100, a["nav"], a["mdd"], np.median(n), n.min(), "—", "—"))
    else:
        print("  %-24s%6.0f%%%8.2f배%8.1f%%%10.2f배%9.2f배%7d/%d%6d/%d"
              % (lbl, a["expo"] * 100, a["nav"], a["mdd"], np.median(n), n.min(),
                 (n > BN).sum(), NS, (m > BM).sum(), NS))
    log("  %s 끝" % lbl)
print("\n  ※ '자산승'은 같은 시드끼리 견줘 이 구성이 지금보다 나은 횟수다. %d/%d 이 동전이다."
      % (NS // 2, NS))

sec("③ 경로분포 — 낙폭 꼬리와 언더워터")
print("  %-24s%10s%10s%9s%9s%14s%11s"
      % ("", "실제낙폭", "낙폭중앙", "하위5%", "하위1%", "언더워터 하위5%", "자산하위5%"))
for lbl in ("지금 (6규칙)", "N1 빼기", "N1 빼고 N6 10/자리4", "N1 자리 4→2"):
    S, P, _, _, _ = OUT[lbl]
    a = sim(S, P, curve=True)
    mm = a["cv"].assign(ym=a["cv"].date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100
    Pt = block_paths(mm, n_paths=5000, mean_block=3)
    print("  %-24s%9.1f%%%9.1f%%%8.1f%%%8.1f%%%12.1f년%10.2f배"
          % (lbl, a["mdd"], Pt.mdd.median(), np.percentile(Pt.mdd, 5),
             np.percentile(Pt.mdd, 1), np.percentile(Pt.under, 95) / 12,
             np.percentile(Pt.nav, 5)))

sec("④ 노출 — N1을 빼면 그 자리를 누가 메우나")
for lbl in ("지금 (6규칙)", "N1 빼기", "N1 빼고 N6 10/자리4"):
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

sec("⑤ 연도별 계좌 — N1이 짐이 된 해가 따로 있나")
print("  %-24s" % "구성" + "".join("%9s" % y for y in range(2016, 2027)))
for lbl in ("지금 (6규칙)", "N1 빼기", "N1 자리 4→2"):
    S, P, _, _, _ = OUT[lbl]
    a = sim(S, P, curve=True)
    cv = a["cv"].assign(y=a["cv"].date.str[:4])
    last = cv.groupby("y").nav.last()
    first = cv.groupby("y").nav.first()
    row = ""
    for y in range(2016, 2027):
        k = str(y)
        row += ("%8.0f%%" % ((last[k] / first[k] - 1) * 100)) if k in last.index else "%9s" % "—"
    print("  %-24s%s" % (lbl, row))
print("\n총 %.0f초" % (time.time() - t0))
