# -*- coding: utf-8 -*-
"""**[자사주 낙폭] 정본 정의로 다시 잰다** (2026-09-15).

us_verify 의 재구성이 사이트 신호의 **2.35배**(3,393 vs 1,441)로 헐거웠다. 그 위에서 잰
계좌 성적(평균 -2.61% · 승률 46% · 노출1%당 -0.12)은 믿을 수 없다.

원인을 찾았다 — 정본(us_buyback5.py)은 SEC XBRL 의 자사주 집행 보고 중
**보고 기간이 60~200일인 것만** 쓴다(= 분기 보고). us_verify 는 그 필터 없이 전부 써서
월별·연간 보고까지 '집행 중' 으로 세었다. 창도 정본은 60거래일 rolling, 재구성은 88캘린더일.

  ① 정본 정의로 다시 만들어 **사이트 신호 1,441건과 대조**
  ② 규칙 단위 성적 (사이트 설명문 숫자와 대조)
  ③ 계좌 — 나머지 넷은 캐시 그대로 두고 [자사주 낙폭]만 갈아 끼운다
  ④ 자리·비중 조정

    python us_n4_fix.py
"""
import pickle, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
NS = 30
W = 108
NM = {"N1": "상승장 신고가", "N2": "낙폭과대", "N3": "저PBR 낙폭",
      "N4": "자사주 낙폭", "N5": "잔잔한 급등주"}


def sec(t):
    print("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


# ── 정본 정의 그대로 (us_buyback5.py 18~50행) ────────────────────────────
B = pd.read_pickle(BASE / "data/us/buyback.pkl")
K = pd.read_pickle(BASE / "data/us_scan.pkl")
K = K[((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
ud = sorted(K.date.unique())
DD = {d: i for i, d in enumerate(ud)}
K["amt_q"] = K.groupby("date").amt20.rank(pct=True)
UNI = (K.amt_q >= 0.6).fillna(False)

SP = B[B.tag == "spend"].copy()
SP["days"] = (pd.to_datetime(SP.end, errors="coerce") - pd.to_datetime(SP.start, errors="coerce")).dt.days
SP = SP[(SP.days >= 60) & (SP.days <= 200) & (SP.val > 0)]   # 분기 보고만 — 여기가 핵심이다
SP = SP.sort_values("days").drop_duplicates(["ticker", "filed"], keep="first")
SP = SP.rename(columns={"filed": "date"})[["ticker", "date", "val"]].rename(columns={"val": "bbspend"})
K = K.merge(SP, on=["ticker", "date"], how="left")
g = K.groupby("ticker", sort=False)
K["sp60"] = g.bbspend.transform(lambda s: s.rolling(60, min_periods=1).count()) > 0
STATE = (UNI & (K.fromhi <= -30) & K.sp60 & (K.ret20 <= -20)).fillna(False)


def event(state, w=20):
    """오늘 처음 들어왔다 — 최근 w거래일은 조건 밖이었다."""
    seen = (state.groupby(K.ticker).shift(1).fillna(False).astype(bool)
            .groupby(K.ticker).transform(lambda s: s.rolling(w, min_periods=1).max()).fillna(0) > 0)
    return (state & ~seen).fillna(False)


def dedup(z, h):
    z = z.sort_values("date")
    keep, last = [], {}
    for t, d_, ix in zip(z.ticker.values, z.date.values, z.index):
        i = DD[d_]
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h
        keep.append(ix)
    return z.loc[keep]


EV = event(STATE)
sec("① 정본 정의로 재구성 — 사이트 신호 건수와 대조")
print("  자사주 spend 보고 %s행 → 분기(60~200일)만 %s행" % (f"{len(B[B.tag=='spend']):,}", f"{len(SP):,}"))
for lbl, c in (("상태형(STATE)", STATE), ("사건형(EV) ← 사이트가 쓰는 것", EV)):
    z = K[c].dropna(subset=["n60"]).copy()
    z = z[(z.buy > 0) & (z.date >= "20160101")]
    z = dedup(z, 60)
    print("  %-34s%7s건   (사이트 1,441)   비율 %5.2fx" % (lbl, f"{len(z):,}", len(z) / 1441))

sec("② 규칙 단위 — 사이트 설명문 숫자와 대조")
print("  사이트: 1,441건 · 평균 +8.03% · 중앙 +6.78% · 승률 62.5% · 절삭 +4.57% · 초과 +1.54%p · 양수해 9/11")
z = K[EV].dropna(subset=["n60"]).copy()
z = z[(z.buy > 0) & (z.date >= "20160101")]
Z = dedup(z, 60).copy()
Z["r"] = Z.n60.astype(float)
BEN = K[UNI].dropna(subset=["n60"]).groupby("date").n60.mean()
Z["ex"] = Z.r - Z.date.map(BEN)
Z["yr"] = Z.date.str[:4]
trim = Z.r[Z.r <= Z.r.quantile(0.95)].mean()
yr = Z.groupby("yr").r.median()
print("  재구성: %s건 · 평균 %+.2f%% · 중앙 %+.2f%% · 승률 %.1f%% · 절삭 %+.2f%% · 초과 %+.2f%%p · 양수해 %d/%d"
      % (f"{len(Z):,}", Z.r.mean(), Z.r.median(), (Z.r > 0).mean() * 100, trim, Z.ex.mean(),
         (yr > 0).sum(), len(yr)))

# ── ③ 계좌 — 캐시의 N4 를 갈아 끼운다 ────────────────────────────────────
with open(BASE / "data" / "sector_drop_us_sig.pkl", "rb") as f:
    C = pickle.load(f)
S0, DS, ADI, PCT0 = C["S"], C["DS"], C["ADI"], C["PCT"]
N = Z[Z.date.isin(set(DS))]
NEW = pd.DataFrame({"date": N.date.values, "ticker": N.ticker.values,
                    "di": [ADI[d] for d in N.date.values], "rid": "N4",
                    "pct": 5, "mx": 3, "hold": 60, "ret": N.r.values, "amt20": N.amt20.values})
S1 = pd.concat([S0[S0.rid != "N4"], NEW], ignore_index=True).sort_values("di").reset_index(drop=True)
print("\n  캐시의 [자사주 낙폭] %s건 → 정본 %s건 으로 교체"
      % (f"{int((S0.rid=='N4').sum()):,}", f"{len(NEW):,}"))


def sim(S, PCT, ds, seed=None, cash_cap=1.0, mxover=None, pctover=None):
    rng = np.random.default_rng(seed) if seed is not None else None
    nav, held, cnt = 1.0, {}, {}
    P = dict(PCT)
    if pctover:
        P.update(pctover)
    byd = {d: gg for d, gg in S[S.date.isin(set(ds))].groupby("date")}
    peak, mdd, inv, log = 1.0, 0.0, [], []
    for d in ds:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            nav *= 1 + held.pop(k)[1] / 100
            cnt[k[0]] = cnt.get(k[0], 0) - 1
        peak = max(peak, nav)
        mdd = min(mdd, nav / peak - 1)
        inv.append(sum(P[k[0]] for k in held) / 100)
        gg = byd.get(d)
        if gg is None:
            continue
        gg = (gg.sample(frac=1, random_state=int(rng.integers(1 << 30))) if rng is not None
              else gg.sort_values("amt20", ascending=False, na_position="last"))
        for r in gg.itertuples():
            mx = (mxover or {}).get(r.rid, r.mx)
            pc = P[r.rid]
            if cnt.get(r.rid, 0) >= mx:
                continue
            k = (r.rid, r.ticker, d)
            if k in held:
                continue
            if sum(P[x[0]] for x in held) / 100 + pc / 100 > cash_cap:
                continue
            held[k] = (di + int(r.hold), r.ret * pc / 100)
            cnt[r.rid] = cnt.get(r.rid, 0) + 1
            log.append((r.rid, r.ret, pc / 100))
    for v in held.values():
        nav *= 1 + v[1] / 100
    return dict(nav=nav, mdd=mdd * 100, expo=float(np.mean(inv)),
                L=pd.DataFrame(log, columns=["rid", "ret", "amt"]))


sec("③ 계좌 — [자사주 낙폭]만 정본으로 갈아 끼우면")
a0, a1 = sim(S0, PCT0, DS), sim(S1, PCT0, DS)
r0 = [sim(S0, PCT0, DS, seed=k) for k in range(NS)]
r1 = [sim(S1, PCT0, DS, seed=k) for k in range(NS)]
wn = sum(1 for x, y in zip(r1, r0) if x["nav"] > y["nav"])
wm = sum(1 for x, y in zip(r1, r0) if x["mdd"] > y["mdd"])
print("  %-22s%7s%9s%9s%11s%8s%8s" % ("구성", "노출", "자산", "낙폭", "30시드중앙", "자산승", "낙폭승"))
print("  %-22s%6.0f%%%8.2f배%8.1f%%%10.2f배%8s%8s"
      % ("헐거운 재구성(전)", a0["expo"] * 100, a0["nav"], a0["mdd"],
         np.median([x["nav"] for x in r0]), "—", "—"))
print("  %-22s%6.0f%%%8.2f배%8.1f%%%10.2f배%6d/%d%6d/%d"
      % ("정본 정의(후)", a1["expo"] * 100, a1["nav"], a1["mdd"],
         np.median([x["nav"] for x in r1]), wn, NS, wm, NS))

sec("④ 규칙별 — 정본으로 바꾼 뒤")
for tag, a in (("전(헐거움)", a0), ("후(정본)", a1)):
    print("\n  [%s]  %-16s%7s%9s%7s%10s" % (tag, "규칙", "체결", "평균%", "승률", "기여%p"))
    for r in ["N1", "N2", "N3", "N4", "N5"]:
        z2 = a["L"][a["L"].rid == r]
        if not len(z2):
            continue
        print("  %-12s%-16s%7s%+9.2f%7.0f%%%+10.1f"
              % ("", NM[r], f"{len(z2):,}", z2.ret.mean(), (z2.ret > 0).mean() * 100,
                 (z2.amt * z2.ret / 100).sum() * 100))

sec("⑤ 정본 기준 — [자사주 낙폭] 자리·비중 조정")
print("  %-22s%7s%9s%9s%11s%8s%8s" % ("구성", "노출", "자산", "낙폭", "30시드중앙", "자산승", "낙폭승"))
for lbl, mxo, pco in (("자리 3 · 비중 5 (지금)", None, None),
                      ("자리 5", {"N4": 5}, None), ("자리 2", {"N4": 2}, None),
                      ("비중 8", None, {"N4": 8}), ("비중 3", None, {"N4": 3}),
                      ("자리 5 · 비중 8", {"N4": 5}, {"N4": 8})):
    a = sim(S1, PCT0, DS, mxover=mxo, pctover=pco)
    rr = [sim(S1, PCT0, DS, seed=k, mxover=mxo, pctover=pco) for k in range(NS)]
    w1 = sum(1 for x, y in zip(rr, r1) if x["nav"] > y["nav"])
    w2 = sum(1 for x, y in zip(rr, r1) if x["mdd"] > y["mdd"])
    print("  %-22s%6.0f%%%8.2f배%8.1f%%%10.2f배%6d/%d%6d/%d"
          % (lbl, a["expo"] * 100, a["nav"], a["mdd"],
             np.median([x["nav"] for x in rr]), w1, NS, w2, NS))
