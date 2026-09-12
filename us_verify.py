# -*- coding: utf-8 -*-
"""**미장 유니버스 조이기(a240 상위20%) 본검증** (2026-09-13).

us_bull20.py 는 N1·N5 를 근사하고 N4 를 통째로 뺀 재구성 위에서 쟀다(기준선 2.58배 vs
사이트 14.42배). 여기서는 **사이트와 같은 정의**로 다시 만들어 셋을 한다.

  ① 진짜 N1~N5 재구성 — collect_us_daily.py 의 nh5·remo·pinr·hl20·absr·qage·bbnew 를
     그대로 옮기고, **사이트에 적힌 신호 건수와 대조**해 충실한지 먼저 확인한다.
  ② 랜덤 30시드 — 자리 경쟁의 운을 지우고 짝비교한다.
  ③ 다중검정 보정 — verdict.deflated_sharpe (1단계 930칸 + 2단계 이후 누적).

    python us_verify.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
W = 116


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)


log("us_scan.pkl 읽는 중")
K = pd.read_pickle(BASE / "data/us_scan.pkl")
K = K[((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)]
K = K[["date", "ticker", "amt20", "buy", "cost", "a240", "u", "PBR", "부채비율", "rawclose",
       "su1", "ret20", "n5", "n10", "n20", "n40", "n60"]].copy()
log("panel_us.pkl 에서 OHLCV 붙이는 중")
P = pd.read_pickle(BASE / "data/panel_us.pkl")[["ticker", "date", "high", "low", "close", "volume"]]
n0 = len(K); K = K.merge(P, on=["ticker", "date"], how="left"); del P
assert len(K) == n0
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
K = K[K.close.notna()]
ud = sorted(K.date.unique()); ADI = {d: i for i, d in enumerate(ud)}
K["di"] = K.date.map(ADI).astype(np.int32)
G = K.groupby("ticker", sort=False)
log(f"  {len(K):,}행 · {K.ticker.nunique():,}종목")

# ── 사이트와 같은 재료 ────────────────────────────────────────────────
R = G.close.pct_change() * 100
K["ret1"] = R
hi250 = G.high.transform(lambda s: s.rolling(250).max())
K["fromhi"] = (K.close / hi250 - 1) * 100
within = (K.fromhi >= -5)


def first_event(state, back=20):
    """오늘 참인데 직전 back 봉 내내 거짓 — 사이트의 nh5·bbnew·qnew 와 같은 설계."""
    s = state.fillna(False)
    prev = s.groupby(K.ticker).transform(lambda x: x.shift(1).rolling(back, min_periods=1).max())
    return (s & (prev.fillna(0) == 0)).fillna(False)


K["nh5"] = first_event(within)
v3 = G.volume.transform(lambda s: s.rolling(3).mean())
vmo = G.volume.transform(lambda s: s.shift(3).rolling(20).mean())
K["remo"] = v3 / vmo * 100
v20 = R.groupby(K.ticker).transform(lambda s: s.rolling(20).std())
v250 = R.groupby(K.ticker).transform(lambda s: s.rolling(250).std())
K["pinr"] = v20 / v250
c20hi = G.close.transform(lambda s: s.rolling(20).max())
c20lo = G.close.transform(lambda s: s.rolling(20).min())
K["hl20"] = (c20hi / c20lo - 1) * 100
K["absr"] = R.abs().groupby(K.ticker).transform(lambda s: s.rolling(60).mean())
for k in (60, 120, 250):
    K[f"r{k}"] = (K.close / G.close.shift(k) - 1) * 100
K["ret60"], K["ret120"], K["ret250"] = K.r60, K.r120, K.r250

# 유동성 — 사이트 usliq = 그날 미장 전체 거래대금 상위 40%
AMTQ = K.groupby("date").amt20.rank(pct=True)
USLIQ = (AMTQ >= 0.60).fillna(False)
A240Q = K.groupby("date").a240.rank(pct=True)

import FinanceDataReader as fdr
IX = fdr.DataReader("US500", "2004-06-01"); IX = IX[IX.Close > 0].copy()
IX["date"] = IX.index.strftime("%Y%m%d"); IX["ma60"] = IX.Close.rolling(60).mean()
UP = K.date.map(dict(zip(IX.date, IX.Close > IX.ma60))).fillna(False)
DN = ~UP

# ── 자사주 집행중 (최근 88일 안에 spend 보고) ──────────────────────────
log("자사주 이력 붙이는 중")
BB = pd.read_pickle(BASE / "data/us/buyback.pkl")
BB = BB[(BB.tag == "spend") & (BB.val.astype(float) > 0)][["ticker", "filed"]].dropna()
BB["filed"] = BB.filed.astype(str)
BB = BB.drop_duplicates().sort_values(["ticker", "filed"])
bbmap = BB.groupby("ticker").filed.apply(lambda s: np.array(sorted(s))).to_dict()
d1 = pd.to_datetime(K.date, format="%Y%m%d")
d0 = (d1 - pd.Timedelta(days=88)).dt.strftime("%Y%m%d").values
dd = K.date.values; tk = K.ticker.values
act = np.zeros(len(K), bool)
cur, arr = None, None
for i in range(len(K)):
    if tk[i] != cur:
        cur = tk[i]; arr = bbmap.get(cur)
    if arr is None or not len(arr): continue
    lo = np.searchsorted(arr, d0[i], "left"); hi = np.searchsorted(arr, dd[i], "right")
    act[i] = hi > lo
K["bbact"] = act
log(f"  자사주 집행중 {act.mean()*100:.1f}%")

# ── 규칙 ─────────────────────────────────────────────────────────────
DEAD = ((K.pinr < 0.5) & (K.hl20 < 8)).fillna(False)          # 가격이 죽은 종목
N1 = (USLIQ & UP & K.nh5 & (K.remo <= 100) & ~DEAD & (K.rawclose >= 3)).fillna(False)
# ⚠ N2·N3 는 usliq(상위40%)를 **쓰지 않는다** — 절대 문턱(거래대금 $2M · 주가 $3)만 본다.
#   처음에 usliq 를 덧붙였다가 신호가 사이트의 0.5배로 줄었다. 사이트 fn 을 그대로 옮길 것.
N2 = (DN & (K.ret20 <= -30) & (K.su1 >= 2) & (K.u <= -10)
      & (K["부채비율"].isna() | (K["부채비율"] <= 200)) & (K.amt20 >= 2) & (K.rawclose >= 3)).fillna(False)
N3 = (DN & (K.PBR > 0) & (K.PBR <= 0.8) & (K.ret20 <= -10) & (K.su1 >= 2)
      & (K.u <= -10) & (K.amt20 >= 2) & (K.rawclose >= 3)).fillna(False)
bb_state = (K.fromhi <= -30) & (K.ret20 <= -20) & K.bbact
N4 = (USLIQ & first_event(bb_state) & (K.rawclose >= 3)).fillna(False)
q_state = (K.r250 >= 120) & (K.r60 > 0) & (K.r120 > 0) & (K.absr <= 1.5)
QNEW = first_event(q_state)
qage = QNEW.groupby(K.ticker).transform(
    lambda s: (np.arange(len(s)) - pd.Series(np.where(s.values, np.arange(len(s)), np.nan),
                                             index=s.index).ffill()))
N5 = (USLIQ & (qage <= 3) & (K.rawclose >= 3)).fillna(False)

sec("① 재구성 검증 — 사이트에 적힌 신호 건수와 맞나 (2016~26 · 중복제거 후)")
SITE = {"N1": 6500, "N2": 2122, "N3": 1544, "N4": 1441, "N5": 516}
HOLD = {"N1": 40, "N2": 20, "N3": 40, "N4": 60, "N5": 60}
PCT = {"N1": 10, "N2": 5, "N3": 5, "N4": 5, "N5": 5}
MX = {"N1": 4, "N2": 3, "N3": 3, "N4": 3, "N5": 3}
CONDS = {"N1": N1, "N2": N2, "N3": N3, "N4": N4, "N5": N5}


def dedup(cond, h, lo="20160101"):
    Z = K[cond].dropna(subset=[f"n{h}"]).copy()
    Z = Z[(Z.buy > 0)].sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(Z.ticker.values, Z.di.values, Z.index):
        if last.get(t, -10 ** 9) >= i: continue
        last[t] = i + h; keep.append(ix)
    Z = Z.loc[keep]
    return Z[Z.date >= lo] if lo else Z


print(f"  {'규칙':<5}{'사이트':>8}{'재구성':>8}{'비율':>8}   판정")
for r in ("N1", "N2", "N3", "N4", "N5"):
    z = dedup(CONDS[r], HOLD[r])
    rt = len(z) / SITE[r]
    print(f"  {r:<5}{SITE[r]:>8,}{len(z):>8,}{rt:>7.2f}x   "
          + ("✅ 비슷하다" if 0.6 <= rt <= 1.6 else "⚠ 많이 다르다 — 정의가 어긋났을 수 있다"))

# ══════════════════════════════════════════════════════════════════════
RULES = {r: dict(cond=CONDS[r], hold=HOLD[r], pct=PCT[r], mx=MX[r]) for r in CONDS}


def build(ids, tight=None):
    out = []
    for r in ids:
        v = RULES[r]; h = v["hold"]
        c = v["cond"] if tight is None else (v["cond"] & tight)
        Z = K[c.fillna(False)].dropna(subset=[f"n{h}"]).copy()
        Z = Z[Z.buy > 0].sort_values("di")
        keep, last = [], {}
        for t, i, ix in zip(Z.ticker.values, Z.di.values, Z.index):
            if last.get(t, -10 ** 9) >= i: continue
            last[t] = i + h; keep.append(ix)
        Z = Z.loc[keep].copy()
        Z["ret"] = Z[f"n{h}"].astype(float); Z["rid"] = r
        Z["pct"] = v["pct"]; Z["mx"] = v["mx"]; Z["hold"] = h
        out.append(Z[["date", "ticker", "di", "rid", "pct", "mx", "hold", "ret", "amt20"]])
    return pd.concat(out).sort_values("di").reset_index(drop=True)


def sim(S, ds, scale=1.0, seed=None, cash_cap=1.0, curve=False):
    rng = np.random.default_rng(seed) if seed is not None else None
    nav, held, cnt = 1.0, {}, {}
    byd = {d: g for d, g in S[S.date.isin(set(ds))].groupby("date")}
    peak, mdd, inv, cv = 1.0, 0.0, [], []
    for d in ds:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            nav *= 1 + held.pop(k)[1] / 100; cnt[k[0]] = cnt.get(k[0], 0) - 1
        peak = max(peak, nav); mdd = min(mdd, nav / peak - 1)
        inv.append(sum(RULES[k[0]]["pct"] * scale for k in held) / 100)
        if curve: cv.append((d, nav))
        g = byd.get(d)
        if g is None: continue
        g = (g.sample(frac=1, random_state=int(rng.integers(1 << 30))) if rng is not None
             else g.sort_values("amt20", ascending=False, na_position="last"))
        for r in g.itertuples():
            if cnt.get(r.rid, 0) >= r.mx: continue
            k = (r.rid, r.ticker, d)
            if k in held: continue
            if sum(RULES[x[0]]["pct"] * scale for x in held) / 100 + r.pct * scale / 100 > cash_cap: continue
            held[k] = (di + int(r.hold), r.ret * r.pct * scale / 100); cnt[r.rid] = cnt.get(r.rid, 0) + 1
    for v in held.values(): nav *= 1 + v[1] / 100
    return (nav, mdd * 100, float(np.mean(inv)), pd.DataFrame(cv, columns=["date", "nav"]) if curve else None)


T20 = (A240Q >= 0.8).fillna(False)
DS = [d for d in ud if d >= "20160101"]
ALL5 = ["N1", "N2", "N3", "N4", "N5"]
NO4 = ["N1", "N2", "N3", "N5"]

sec("② 계좌 — 거래대금 큰 순(정본 정책) · 노출 맞춤 · 기준 2016~")
print(f"  {'구성':<28}{'배율':>5}{'노출':>7}{'자산':>9}{'낙폭':>8}")
OUT = {}
for nm, ids, tg in (("다섯 규칙 (지금)", ALL5, None), ("다섯 규칙 · a240 상위20%", ALL5, T20),
                    ("N4 빼고 (지금)", NO4, None), ("N4 빼고 · a240 상위20%", NO4, T20)):
    S = build(ids, tg)
    for sc in (0.6, 0.8, 1.0, 1.2, 1.5):
        nav, mdd, ex, _ = sim(S, DS, sc)
        OUT[(nm, sc)] = (ex * 100, nav, mdd)
        print(f"  {nm if sc == 0.6 else '':<28}{sc:>5.1f}{ex*100:>6.0f}%{nav:>8.2f}배{mdd:>7.1f}%")
    print()


def at(nm, t):
    p = sorted(OUT[(nm, s)] for s in (0.6, 0.8, 1.0, 1.2, 1.5)); xs = [a[0] for a in p]
    if t < xs[0] or t > xs[-1]: return None
    for i in range(len(p) - 1):
        if xs[i] <= t <= xs[i + 1]:
            w = (t - xs[i]) / max(xs[i + 1] - xs[i], 1e-9)
            return p[i][1] + w * (p[i + 1][1] - p[i][1]), p[i][2] + w * (p[i + 1][2] - p[i][2])


TGT = OUT[("다섯 규칙 (지금)", 1.0)][0]
print(f"  같은 노출({TGT:.0f}%)에서")
for nm in ("다섯 규칙 (지금)", "다섯 규칙 · a240 상위20%", "N4 빼고 (지금)", "N4 빼고 · a240 상위20%"):
    v = at(nm, TGT)
    print(f"    {nm:<28}" + (f"{v[0]:>8.2f}배   낙폭 {v[1]:>6.1f}%" if v else "  (범위 밖)"))

sec("③ 랜덤 30시드 짝비교 (배율 1.0 · 기준 2016~)")
NS = 30
res = {}
for nm, ids, tg in (("지금 (usliq 상위40%)", ALL5, None), ("a240 상위20%로 조임", ALL5, T20)):
    S = build(ids, tg)
    rows = [sim(S, DS, 1.0, seed=k)[:3] for k in range(NS)]
    res[nm] = pd.DataFrame(rows, columns=["nav", "mdd", "expo"])
    d = res[nm]
    print(f"  {nm:<24} 중앙 {d.nav.median():>6.2f}배 · 최악 {d.nav.min():>5.2f} · 최고 {d.nav.max():>5.2f}"
          f" · 낙폭 중앙 {d.mdd.median():>6.1f}% · 최악 {d.mdd.min():>6.1f}% · 노출 {d.expo.mean()*100:>3.0f}%")
a, b = res["지금 (usliq 상위40%)"], res["a240 상위20%로 조임"]
dn = b.nav.values - a.nav.values; dm = b.mdd.values - a.mdd.values
print(f"\n  같은 시드에서 조인 쪽이 자산 큼 {int((dn>0).sum())}/{NS} · 차이 중앙 {np.median(dn):+.2f}배")
print(f"  같은 시드에서 조인 쪽이 낙폭 얕음 {int((dm>0).sum())}/{NS} · 차이 중앙 {np.median(dm):+.1f}%p")

sec("④ 다중검정 보정 — 이 탐색에서 시험한 칸 수를 감안해도 남는가")
S0 = build(ALL5, None); S1 = build(ALL5, T20)
_, _, _, c0 = sim(S0, DS, 1.0, curve=True)
_, _, _, c1 = sim(S1, DS, 1.0, curve=True)
m0 = c0.assign(ym=c0.date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100
m1 = c1.assign(ym=c1.date.str[:6]).groupby("ym").nav.last().pct_change().dropna() * 100
diff = (m1 - m0).dropna()
try:
    from verdict import deflated_sharpe, boot_ci as vboot, trial_count, log_trials
    log_trials("us_bull_short", 250)
    nt = max(trial_count("us_bull_short") or 0, 1180)
    print(f"  누적 시험 칸수 {nt:,} (1단계 930 + 2·3단계)")
    print(f"  월수익 차이(조임-지금): 평균 {diff.mean():+.3f}%p · 월 {len(diff)}개")
    print(f"  90% 신뢰구간 하한 {vboot(diff.values):+.3f}%p")
    print(f"  Deflated Sharpe {deflated_sharpe(diff.values, nt)*100:.1f}%  (95% 이상이어야 통과)")
except Exception as e:
    print(f"  보정 실패: {e!r}")
log("끝")
