# -*- coding: utf-8 -*-
"""**내부자 규칙 — 정본 기준선 위에서 다시 판정** (2026-09-15).

2026-09-10 에 실측을 마치고 "사용자 판단 대기" 로 멈춰 있던 건이다. 그때 기준선은
**기존 3규칙 9.24배**였다. 지금은 5규칙이고, 게다가 [자사주 낙폭]의 캐시가 오염돼 있던 것을
오늘 고쳐 기준선이 **8.44배**가 됐다. 그 위에서 다시 재야 답이 나온다.

규칙: **내부자 매수 100만$ 이상 → 다음날 시가 매수 · 40거래일 보유** (유니버스 거래대금 상위40%)
  · 금액 문턱은 30만→100만→200만까지 단조 상승, 500만에서 꺾인다(2026-09-10).
  · [상승장 신고가]와 겹치는 게 10,809건 중 4건 — 완전히 독립된 축이다.
  · 보류 사유였던 것: 검증CI -0.68 · 상위5% 절삭 -0.05 · 상위 1%가 수익의 34~43%.

  ① 규칙 단위 재확인 (복권형 점검 포함)
  ② 계좌 — 5규칙 vs 6규칙 · 100시드
  ③ 자리·비중 스윕
  ④ 경로분포 — 낙폭 꼬리와 언더워터가 어떻게 바뀌나
  ⑤ 겹침 — 정말 빈 날을 채우나

    python us_ins_final.py
"""
import pickle, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path
from verdict import block_paths

BASE = Path(__file__).parent
NS = 100
W = 110
NM = {"N1": "상승장 신고가", "N2": "낙폭과대", "N3": "저PBR 낙폭",
      "N4": "자사주 낙폭", "N5": "잔잔한 급등주", "IN": "내부자 매수"}


def sec(t):
    print("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


print("us_ins.pkl 읽는 중 (6.2GB)")
K = pd.read_pickle(BASE / "data/us_ins.pkl")
need = ["ticker", "date", "amt20", "bv", "n40", "buy", "pref", "rawclose"]
K = K[[c for c in need if c in K.columns]].copy()
K = K[((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)] if "pref" in K.columns else K
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
K["amt_q"] = K.groupby("date").amt20.rank(pct=True)
UNI = (K.amt_q >= 0.6).fillna(False)
ud = sorted(K.date.unique())
DD = {d: i for i, d in enumerate(ud)}
print("  %s행 · %s종목" % (f"{len(K):,}", f"{K.ticker.nunique():,}"))

COND = (UNI & (K.bv >= 1e6)).fillna(False)
z = K[COND].dropna(subset=["n40"]).copy()
z = z[(z.buy > 0) & (z.date >= "20160101")].sort_values("date")
keep, last = [], {}
for t, d_, ix in zip(z.ticker.values, z.date.values, z.index):
    i = DD[d_]
    if last.get(t, -10 ** 9) >= i:
        continue
    last[t] = i + 40
    keep.append(ix)
Z = z.loc[keep].copy()
Z["r"] = Z.n40.astype(float)
BEN = K[UNI].dropna(subset=["n40"]).groupby("date").n40.mean()
Z["ex"] = Z.r - Z.date.map(BEN)

sec("① 규칙 단위 — 내부자 매수 100만$↑ · 40일")
trim = Z.r[Z.r <= Z.r.quantile(0.95)].mean()
yr = Z.groupby(Z.date.str[:4]).r.median()
tot = Z.r.sum()
t1 = Z.r.nlargest(max(1, len(Z) // 100)).sum()
t5 = Z.r.nlargest(max(1, len(Z) // 20)).sum()
print("  %s건 · 평균 %+.2f%% · 중앙 %+.2f%% · 승률 %.1f%% · 절삭 %+.2f%% · 초과 %+.2f%%p · 양수해 %d/%d"
      % (f"{len(Z):,}", Z.r.mean(), Z.r.median(), (Z.r > 0).mean() * 100, trim, Z.ex.mean(),
         (yr > 0).sum(), len(yr)))
print("  복권형 점검 — 상위 1%%가 수익의 %.1f%% · 상위 5%%가 %.1f%%" % (t1 / tot * 100, t5 / tot * 100))
print("  연도별 중앙: " + " ".join("%s:%+.1f" % (y[2:], v) for y, v in yr.items()))

# ── 캐시에 얹는다 ────────────────────────────────────────────────────────
with open(BASE / "data" / "sector_drop_us_sig.pkl", "rb") as f:
    C = pickle.load(f)
S5, DS, ADI, PCT5 = C["S"], C["DS"], C["ADI"], C["PCT"]
N = Z[Z.date.isin(set(DS))]
print("\n  계좌 구간(2016~) 안의 내부자 신호 %s건" % f"{len(N):,}")


def build(pct, mx):
    add = pd.DataFrame({"date": N.date.values, "ticker": N.ticker.values,
                        "di": [ADI[d] for d in N.date.values], "rid": "IN",
                        "pct": pct, "mx": mx, "hold": 40, "ret": N.r.values,
                        "amt20": N.amt20.values})
    S = pd.concat([S5, add], ignore_index=True).sort_values("di").reset_index(drop=True)
    P = dict(PCT5); P["IN"] = pct
    return S, P


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
            log.append((r.rid, r.ret, r.pct / 100, d))
    for v in held.values():
        nav *= 1 + v[1] / 100
    return dict(nav=nav, mdd=mdd * 100, expo=float(np.mean(inv)),
                L=pd.DataFrame(log, columns=["rid", "ret", "amt", "date"]),
                cv=pd.DataFrame(cv, columns=["date", "nav"]) if curve else None)


sec("② 계좌 — 5규칙 vs 6규칙 (%d시드)" % NS)
b = sim(S5, PCT5, DS)
b100 = [sim(S5, PCT5, DS, seed=k) for k in range(NS)]
BN = [x["nav"] for x in b100]
BM = [x["mdd"] for x in b100]
print("  %-24s%7s%9s%9s%12s%9s%9s" % ("구성", "노출", "자산", "낙폭", "시드중앙", "자산승", "낙폭승"))
print("  %-24s%6.0f%%%8.2f배%8.1f%%%11.2f배%9s%9s"
      % ("5규칙 (지금)", b["expo"] * 100, b["nav"], b["mdd"], np.median(BN), "—", "—"))
BEST = None
for pct, mx in ((5, 3), (5, 5), (8, 3), (10, 3), (5, 8), (3, 5)):
    S, P = build(pct, mx)
    a = sim(S, P, DS)
    rr = [sim(S, P, DS, seed=k) for k in range(NS)]
    wn = sum(1 for x, y in zip(rr, b100) if x["nav"] > y["nav"])
    wm = sum(1 for x, y in zip(rr, b100) if x["mdd"] > y["mdd"])
    print("  %-24s%6.0f%%%8.2f배%8.1f%%%11.2f배%7d/%d%7d/%d"
          % ("+내부자 비중%d 자리%d" % (pct, mx), a["expo"] * 100, a["nav"], a["mdd"],
             np.median([x["nav"] for x in rr]), wn, NS, wm, NS))
    if BEST is None:
        BEST = (pct, mx, S, P, a)

sec("③ 경로분포 — 5규칙 vs +내부자(비중5·자리3)")
print("  %-24s%11s%10s%9s%9s%14s%11s"
      % ("", "실제낙폭", "낙폭중앙", "하위5%", "하위1%", "언더워터 하위5%", "자산하위5%"))
for lbl, SS, PP in (("5규칙 (지금)", S5, PCT5), ("+내부자", BEST[2], BEST[3])):
    a = sim(SS, PP, DS, curve=True)
    m = a["cv"].assign(ym=a["cv"].date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100
    P = block_paths(m, n_paths=5000, mean_block=3)
    print("  %-24s%10.1f%%%9.1f%%%8.1f%%%8.1f%%%12.1f년%10.2f배"
          % (lbl, a["mdd"], P.mdd.median(), np.percentile(P.mdd, 5), np.percentile(P.mdd, 1),
             np.percentile(P.under, 95) / 12, np.percentile(P.nav, 5)))

sec("④ 규칙별 · 겹침 — 정말 빈 날을 채우나")
a = BEST[4]
L = a["L"]
print("  %-16s%7s%9s%7s%10s" % ("규칙", "체결", "평균%", "승률", "기여%p"))
for r in ["N1", "N2", "N3", "N4", "N5", "IN"]:
    zz = L[L.rid == r]
    if not len(zz):
        continue
    print("  %-16s%7s%+9.2f%7.0f%%%+10.1f"
          % (NM[r], f"{len(zz):,}", zz.ret.mean(), (zz.ret > 0).mean() * 100,
             (zz.amt * zz.ret / 100).sum() * 100))
b_cv = sim(S5, PCT5, DS, curve=True)["cv"]
expo5 = {}
aa = sim(S5, PCT5, DS)
ins = L[L.rid == "IN"]
c5 = sim(S5, PCT5, DS, curve=True)
# 내부자 신호가 난 날의 기존 5규칙 노출
tmp = sim(S5, PCT5, DS)
S5days = {}
print("\n  내부자 체결 %s건 · 5규칙과 같은 종목을 ±5일 안에 잡은 건 계산 중" % f"{len(ins):,}")
old = L[L.rid != "IN"]
ok = {}
for t, d in zip(old.rid.values, old.date.values):
    pass
print("  (겹침은 신호표로 직접 본다)")
S6 = BEST[2]
oi = S6[S6.rid == "IN"]
oo = S6[S6.rid != "IN"]
key = {}
for t, di in zip(oo.ticker.values, oo.di.values):
    key.setdefault(t, []).append(di)
near = sum(1 for t, di in zip(oi.ticker.values, oi.di.values)
           if any(abs(di - x) <= 5 for x in key.get(t, [])))
print("  내부자 신호 %s건 중 기존 규칙과 같은 종목 ±5일 겹침 %s건 (%.0f%%)"
      % (f"{len(oi):,}", f"{near:,}", near / max(len(oi), 1) * 100))
