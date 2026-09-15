# -*- coding: utf-8 -*-
"""**미장 핵심 지표 재측정 — 캐시가 오염돼 있었다** (2026-09-15).

[자사주 낙폭]을 정본 정의로 고치니 계좌가 **5.47 → 8.44배**, 낙폭 **-30.0 → -18.4%** 가 됐다.
오늘 미장에 대해 낸 결론은 전부 그 오염된 캐시(us_verify 재구성, N4 신호가 2.7배) 위에서
나온 것이라 **다시 재야 한다**. 특히 이 셋:

  · 미장 낙폭 꼬리 -52.9% · 언더워터 6.9년   ← 이 숫자로 '미장 배율 그대로' 를 정했다
  · [상승장 신고가]의 노출 1%당 효율
  · 배율을 올리면/내리면

캐시(data/sector_drop_us_sig.pkl)도 정본 N4 로 갈아 끼운다 — 앞으로 쓸 도구가 오염된 채
남으면 안 된다. 옛 캐시는 .bak 으로 남긴다.

    python us_recheck.py
"""
import pickle, shutil, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path
from verdict import block_paths

BASE = Path(__file__).parent
NS = 30
W = 108
NM = {"N1": "상승장 신고가", "N2": "낙폭과대", "N3": "저PBR 낙폭",
      "N4": "자사주 낙폭", "N5": "잔잔한 급등주"}
RID = ["N1", "N2", "N3", "N4", "N5"]


def sec(t):
    print("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


# ── 정본 N4 를 다시 만든다 (us_n4_fix.py 와 같은 코드) ────────────────────
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
SP = SP[(SP.days >= 60) & (SP.days <= 200) & (SP.val > 0)]
SP = SP.sort_values("days").drop_duplicates(["ticker", "filed"], keep="first")
SP = SP.rename(columns={"filed": "date"})[["ticker", "date", "val"]].rename(columns={"val": "bbspend"})
K = K.merge(SP, on=["ticker", "date"], how="left")
K["sp60"] = K.groupby("ticker", sort=False).bbspend.transform(
    lambda s: s.rolling(60, min_periods=1).count()) > 0
STATE = (UNI & (K.fromhi <= -30) & K.sp60 & (K.ret20 <= -20)).fillna(False)
seen = (STATE.groupby(K.ticker).shift(1).fillna(False).astype(bool)
        .groupby(K.ticker).transform(lambda s: s.rolling(20, min_periods=1).max()).fillna(0) > 0)
EV = (STATE & ~seen).fillna(False)
z = K[EV].dropna(subset=["n60"]).copy()
z = z[(z.buy > 0) & (z.date >= "20160101")].sort_values("date")
keep, last = [], {}
for t, d_, ix in zip(z.ticker.values, z.date.values, z.index):
    i = DD[d_]
    if last.get(t, -10 ** 9) >= i:
        continue
    last[t] = i + 60
    keep.append(ix)
Z = z.loc[keep]
print("정본 [자사주 낙폭] %s건 (사이트 1,441)" % f"{len(Z):,}")

CACHE = BASE / "data" / "sector_drop_us_sig.pkl"
with open(CACHE, "rb") as f:
    C = pickle.load(f)
S_OLD, DS, ADI, PCT = C["S"], C["DS"], C["ADI"], C["PCT"]
N = Z[Z.date.isin(set(DS))]
NEW = pd.DataFrame({"date": N.date.values, "ticker": N.ticker.values,
                    "di": [ADI[d] for d in N.date.values], "rid": "N4",
                    "pct": 5, "mx": 3, "hold": 60, "ret": N.n60.astype(float).values,
                    "amt20": N.amt20.values})
S = pd.concat([S_OLD[S_OLD.rid != "N4"], NEW], ignore_index=True).sort_values("di").reset_index(drop=True)

# 캐시 교체 — 옛것은 남긴다
shutil.copy(CACHE, str(CACHE) + ".bak")
C["S"] = S
with open(CACHE, "wb") as f:
    pickle.dump(C, f)
print("캐시 갱신 — 옛 캐시는 %s.bak 으로 남겼다" % CACHE.name)


def sim(S, ds, scale=1.0, seed=None, cash_cap=1.0, curve=False, byrule=False):
    rng = np.random.default_rng(seed) if seed is not None else None
    nav, held, cnt = 1.0, {}, {}
    byd = {d: gg for d, gg in S[S.date.isin(set(ds))].groupby("date")}
    peak, mdd, inv, cv, log = 1.0, 0.0, [], [], []
    er = {r: 0.0 for r in PCT}
    for d in ds:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            nav *= 1 + held.pop(k)[1] / 100
            cnt[k[0]] = cnt.get(k[0], 0) - 1
        peak = max(peak, nav)
        mdd = min(mdd, nav / peak - 1)
        inv.append(sum(PCT[k[0]] * scale for k in held) / 100)
        if byrule:
            for k in held:
                er[k[0]] += PCT[k[0]] * scale
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
            if sum(PCT[x[0]] * scale for x in held) / 100 + r.pct * scale / 100 > cash_cap:
                continue
            held[k] = (di + int(r.hold), r.ret * r.pct * scale / 100)
            cnt[r.rid] = cnt.get(r.rid, 0) + 1
            log.append((r.rid, r.ret, r.pct * scale / 100))
    for v in held.values():
        nav *= 1 + v[1] / 100
    return dict(nav=nav, mdd=mdd * 100, expo=float(np.mean(inv)),
                L=pd.DataFrame(log, columns=["rid", "ret", "amt"]),
                cv=pd.DataFrame(cv, columns=["date", "nav"]) if curve else None,
                er={r: v / len(ds) for r, v in er.items()})


YRS = len(DS) / 252
sec("① 미장 계좌 — 오염 전후")
print("  %-20s%7s%9s%9s%12s" % ("", "노출", "자산", "낙폭", "30시드중앙"))
for lbl, SS in (("오염된 캐시(전)", S_OLD), ("정본(후)", S)):
    a = sim(SS, DS)
    r30 = [sim(SS, DS, seed=k)["nav"] for k in range(NS)]
    print("  %-20s%6.0f%%%8.2f배%8.1f%%%11.2f배"
          % (lbl, a["expo"] * 100, a["nav"], a["mdd"], np.median(r30)))

sec("② 경로분포 재측정 — '미장 낙폭 꼬리 -52.9% · 언더워터 6.9년' 은 맞나")
print("  %-20s%11s%10s%9s%9s%14s%11s" % ("", "실제낙폭", "낙폭중앙", "하위5%", "하위1%", "언더워터 하위5%", "자산하위5%"))
for lbl, SS in (("오염된 캐시(전)", S_OLD), ("정본(후)", S)):
    a = sim(SS, DS, curve=True)
    m = a["cv"].assign(ym=a["cv"].date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100
    P = block_paths(m, n_paths=5000, mean_block=3)
    print("  %-20s%10.1f%%%9.1f%%%8.1f%%%8.1f%%%12.1f년%10.2f배"
          % (lbl, a["mdd"], P.mdd.median(), np.percentile(P.mdd, 5), np.percentile(P.mdd, 1),
             np.percentile(P.under, 95) / 12, np.percentile(P.nav, 5)))

sec("③ 규칙별 효율 재측정 — 노출 1%당")
a = sim(S, DS, byrule=True)
tot = sum(a["er"].values())
print("  %-16s%7s%9s%7s%11s%9s%10s%11s" % ("규칙", "체결", "평균%", "승률", "점유 노출", "노출 몫", "기여%p", "노출1%당"))
for r in RID:
    zz = a["L"][a["L"].rid == r]
    e = a["er"][r]
    con = (zz.amt * zz.ret / 100).sum() * 100
    print("  %-16s%7s%+9.2f%7.0f%%%10.1f%%%8.0f%%%+10.1f%11.2f"
          % (NM[r], f"{len(zz):,}", zz.ret.mean(), (zz.ret > 0).mean() * 100, e, e / tot * 100,
             con, con / max(e, 0.01)))

sec("④ 배율 — '미장은 1.0 그대로' 판단이 여전히 맞나")
print("  %-10s%7s%9s%9s%12s%9s%9s" % ("배율", "노출", "자산", "낙폭", "30시드중앙", "자산승", "낙폭승"))
b30 = [sim(S, DS, seed=k) for k in range(NS)]
for s in (0.6, 0.8, 1.0, 1.2, 1.5):
    aa = sim(S, DS, scale=s)
    rr = [sim(S, DS, scale=s, seed=k) for k in range(NS)]
    w1 = sum(1 for x, y in zip(rr, b30) if x["nav"] > y["nav"])
    w2 = sum(1 for x, y in zip(rr, b30) if x["mdd"] > y["mdd"])
    print("  %-10s%6.0f%%%8.2f배%8.1f%%%11.2f배%7d/%d%7d/%d"
          % (str(s) + "배", aa["expo"] * 100, aa["nav"], aa["mdd"],
             np.median([x["nav"] for x in rr]), w1, NS, w2, NS))
