# -*- coding: utf-8 -*-
"""기각된 기법들을 **미장 규칙의 거르개**로 (2026-09-30 사용자: "미장이 규칙이 너무 많이 발생되니 기각된 것들을 얹어서
건수는 줄어도 승률·수익률이 오르는지").

거르개(신호일 종가까지 아는 값만):
  F1 벨레즈      신호일까지 고가가 낮아지는 음봉 3개↑ 연속
  F2 기간조정    20일 최저가 > 그 앞 20일 최저가 & 하락일 거래량 < 상승일 거래량(20일)
  F3 다진 자리   40일 최저 종가 ≥ 120일 최고가 × 0.85
  F4 팔리 밀집   5·10일선 1% 안 & 몸통 1.5% 이하 & 거래량 ≤ 20일 평균 70%
  F5 와조스키    5일선 아래 & 120일선 위 & 5일 거래량 ≤ 60일 평균 70%
  F6 바닥 확인   신호일 캔들이 종가 > 전일 고가 또는 아래꼬리 ≥ 몸통 2배
  F7 조용함      20일 일간 변동성이 그날 유니버스 하위 50%
  F8 달          신월 ±7일(위약 — 말도 안 되는 거르개가 얼마나 흔들리나 보는 잣대)
  F9 동전        난수 50%(순수 위약)
① 거래 단위: 규칙 × 거르개, 남는 쪽 / 빠지는 쪽의 건수·승률·평균·중앙 — 옛날 08~15 / 학습 16~22 / 검증 23~
② 계좌: 미장 6규칙 사이트 비중·자리 그대로(us_capture.sim), 한 규칙에만 거르개 → 2016~ 연수익·최대낙폭(30시드 중앙)
   ①에서 학습·검증 둘 다 평균이 오른 칸만.

    python research/us_filter.py
"""
import glob, io, sys, time, contextlib, pickle, warnings
warnings.filterwarnings("ignore")
sys.argv = [sys.argv[0], "--panel", "us_full_2007.pkl", "--since", "20080101"]
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
with contextlib.redirect_stdout(io.StringIO()):
    import us_surv_measure as M
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from verdict import log_trials

PCT = {"N1": 10, "N2": 5, "N3": 5, "N4": 5, "N5": 5, "N6": 5}
MX = {"N1": 4, "N2": 3, "N3": 3, "N4": 3, "N5": 3, "N6": 3}
HOLD = dict(M.HOLD); HOLD["N6"] = 60
NAME = {"N1": "상승장 신고가", "N2": "낙폭과대", "N3": "저PBR 낙폭", "N4": "자사주 낙폭", "N5": "잔잔한 급등주", "N6": "실적 서프라이즈"}
OUT = []; t0 = time.time()
P = lambda s="": (OUT.append(s), print(s, flush=True))


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


K = M.K
ud = np.array(sorted(K.date.unique())); DI = {d: i for i, d in enumerate(ud)}
C = M.rules(pd.Series(True, index=K.index), "u_all")

# ── 거르개 재료 (종목별) ─────────────────────────────────────────────────
log("거르개 재료")
K = K.sort_values(["ticker", "di"])
g = K.groupby("ticker", sort=False)
c = K.rawclose; h = K.high; l = K.low; v = K.volume
o = g.buy.shift(1)                                     # 전날의 '다음날 시가' = 오늘 시가
o = o.fillna(c)
pc = g.rawclose.shift(1); ph = g.high.shift(1)
bear = (c < o)
lowerh = h < ph
# F1: 고가 낮아지는 음봉 연속 길이
x = (bear & lowerh).astype(int)
x[K.ticker != K.ticker.shift()] = 0
run = x.groupby((x != x.shift()).cumsum()).cumsum() * x
K["f1"] = (run >= 2) & bear.groupby(K.ticker).shift(2).fillna(False)   # 음봉 1개 + 고가 낮아진 음봉 2개 = 음봉 3개
roll = lambda s, n, f: g[s].transform(lambda z: getattr(z.rolling(n, min_periods=int(n * 0.8)), f)())
lo20 = roll("low", 20, "min"); lo40 = g.low.transform(lambda z: z.shift(20).rolling(20, min_periods=16).min())
up = c > pc; dn = c < pc
K["_vu"] = v.where(up); K["_vd"] = v.where(dn)
g2 = K.groupby("ticker", sort=False)
vu = g2._vu.transform(lambda z: z.rolling(20, min_periods=5).mean()); vd = g2._vd.transform(lambda z: z.rolling(20, min_periods=5).mean())
K["f2"] = (lo20 > lo40) & (vd < vu)
h120 = roll("high", 120, "max"); c40 = roll("rawclose", 40, "min")
K["f3"] = c40 >= 0.85 * h120
ma5 = roll("rawclose", 5, "mean"); ma10 = roll("rawclose", 10, "mean"); ma120 = roll("rawclose", 120, "mean")
v20 = g.volume.transform(lambda z: z.shift(1).rolling(20, min_periods=16).mean())
K["f4"] = ((ma5 / ma10 - 1).abs() <= 0.01) & ((c - o).abs() / c <= 0.015) & (v <= 0.7 * v20)
v5 = roll("volume", 5, "mean"); v60 = roll("volume", 60, "mean")
K["f5"] = (c < ma5) & (c > ma120) & (v5 <= 0.7 * v60)
body = (c - o).abs(); lw = np.minimum(o, c) - l
K["f6"] = (c > ph) | ((body > 0) & (lw >= 2 * body))
r1 = g.px.pct_change()
K["_r1"] = r1
vol20 = K.groupby("ticker", sort=False)._r1.transform(lambda z: z.rolling(20, min_periods=16).std())
K["f7"] = vol20.groupby(K.date).rank(pct=True) <= 0.5
ref = pd.Timestamp("2000-01-06 18:14", tz="UTC")
dd = pd.to_datetime(pd.Series(ud), format="%Y%m%d").dt.tz_localize("US/Eastern") + pd.Timedelta(hours=16)
age = ((dd.dt.tz_convert("UTC") - ref).dt.total_seconds() / 86400.0) % 29.530588853
newm = dict(zip(ud, (age <= 7.4) | (age >= 22.1)))
K["f8"] = K.date.map(newm)
K["f9"] = np.random.default_rng(3).random(len(K)) < 0.5
FL = {"f1": "F1 벨레즈 음봉3", "f2": "F2 기간조정", "f3": "F3 다진 자리", "f4": "F4 팔리 밀집", "f5": "F5 와조스키 눌림",
      "f6": "F6 바닥 확인 캔들", "f7": "F7 조용함", "f8": "F8 달(위약)", "f9": "F9 동전(위약)"}
K = K.drop(columns=["_vu", "_vd", "_r1"]).sort_index()
for f in FL:
    K[f] = K[f].fillna(False).astype(bool)

PX = {}
for t, ix in K.groupby("ticker", sort=False).indices.items():
    PX[t] = (K.di.values[ix], K.px.values[ix])


def dedup_all(cond, hh, rid):
    Z = K[(cond & (K.buy > 0)).fillna(False)][["date", "ticker", "di", "buy", "cost", "amt20"] + list(FL)].sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(Z.ticker.values, Z.di.values, Z.index):
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + hh; keep.append(ix)
    Z = Z.loc[keep].copy(); Z["rid"] = rid; Z["hold"] = hh
    return Z


log("신호")
S = pd.concat([dedup_all(C[r], HOLD[r], r) for r in ("N1", "N2", "N3", "N4", "N5")], ignore_index=True)
S = S[S.ticker.isin(PX)].reset_index(drop=True)


def path(t, s, hh, buy):
    di, px = PX[t]
    a = np.searchsorted(di, s + 1); b = np.searchsorted(di, s + hh, "right")
    return di[a:b], px[a:b] / buy


PATH = [path(t, s, hh, b) for t, s, hh, b in zip(S.ticker.values, S.di.values, S.hold.values, S.buy.values)]
S["ok"] = [len(p[0]) > 0 for p in PATH]
S["done"] = [len(p[0]) > 0 and p[0][-1] >= s + hh - 3 for p, s, hh in zip(PATH, S.di.values, S.hold.values)]
S["ret"] = [(p[1][-1] - 1) * 100 - cst if len(p[0]) else np.nan for p, cst in zip(PATH, S.cost.values)]
S["per"] = np.where(S.date <= "20151231", 0, np.where(S.date <= "20221231", 1, 2))

# ── ① 거래 단위 ─────────────────────────────────────────────────────────
P("# 기각 기법을 미장 규칙 거르개로 · %s" % time.strftime("%Y-%m-%d")); P("")
P("폐지 포함 패널(us_full_2007) · 사이트 보유기간 · 거래 = 보유 끝까지(폐지는 마지막 가격) · 비용 차감. 평균/승률."); P("")
PL = ["옛날 08~15", "학습 16~22", "검증 23~"]
T = S[S.done & (S.date >= "20080101")]
good = []
for r in ("N1", "N2", "N3", "N4", "N5"):
    z = T[T.rid == r]
    P("## [%s] %s — 전체 %s건" % (NAME[r], r, f"{len(z):,}")); P("")
    P("| 거르개 | 남는 비율 | " + " | ".join("%s 남음 평균·승률 / 빠짐 평균" % p for p in PL) + " | 판정 |"); P("|---|---|---|---|---|---|")
    base = [z[z.per == i].ret for i in range(3)]
    P("| (전체) | 100%% | " + " | ".join("%+.2f · %.0f%% (%d)" % (b.mean(), (b > 0).mean() * 100, len(b)) for b in base) + " | |")
    for f, nm in FL.items():
        cells, better = [], []
        for i in range(3):
            k = z[(z.per == i) & z[f]].ret; d_ = z[(z.per == i) & ~z[f]].ret
            if len(k) < 15:
                cells.append("n=%d" % len(k)); better.append(None); continue
            cells.append("%+.2f · %.0f%% (%d) / %+.2f" % (k.mean(), (k > 0).mean() * 100, len(k), d_.mean() if len(d_) else np.nan))
            better.append(k.mean() > base[i].mean())
        ok = better[1] is True and better[2] is True
        if ok and f not in ("f8", "f9"):
            good.append((r, f))
        P("| %s | %.0f%% | %s | %s |" % (nm, z[f].mean() * 100, " | ".join(cells), "✅ 학습·검증 둘 다 오름" if ok else ""))
    P("")

# ── ② 계좌 ──────────────────────────────────────────────────────────────
log("계좌 — 후보 %d칸" % len(good))
SA = S[S.date >= "20160101"].copy()
IDX = SA.index.values
PATH_X = None


def sim(Sx, paths, pct, mx, seed):
    rng = np.random.default_rng(seed)
    by = {}
    for n in range(len(Sx)):
        if Sx.ok.values[n]:
            by.setdefault(Sx.di.values[n], []).append(n)
    cash, pos, navs = 1.0, [], np.empty(len(ud))
    cnt = {}
    rid, cost, hold, di0 = Sx.rid.values, Sx.cost.values, Sx.hold.values, Sx.di.values
    for d in range(len(ud)):
        keep, val = [], 0.0
        for p in pos:
            n, alloc, ent = p
            ddi, ratio = paths[n]
            k = np.searchsorted(ddi, d, "right") - 1
            cur = ratio[k] if k >= 0 else 1.0
            if d >= ent + hold[n] or d > ddi[-1]:
                cash += alloc * (cur - cost[n] / 100); cnt[rid[n]] -= 1
            else:
                keep.append(p); val += alloc * cur
        pos = keep
        nav = cash + val; navs[d] = nav
        L = by.get(d)
        if not L:
            continue
        L = list(L); rng.shuffle(L)
        for n in L:
            r = rid[n]
            if cnt.get(r, 0) >= mx[r]:
                continue
            a = nav * pct[r] / 100
            if a > cash + 1e-12:
                continue
            cash -= a; pos.append((n, a, d)); cnt[r] = cnt.get(r, 0) + 1
    return pd.Series(navs, index=ud)


def acct(mask, seeds=30):
    Sx = SA[mask].reset_index(drop=True)
    paths = [PATH[i] for i in SA.index[mask]]
    res = []
    for s in range(seeds):
        nav = sim(Sx, paths, PCT, MX, s)
        nav = nav[nav.index >= "20160101"]
        out = {}
        for lab, a in (("16~", "20160101"), ("21~", "20210101"), ("23~", "20230101")):
            z = nav[nav.index >= a]; z = z / z.iloc[0]
            yrs = len(z) / 252
            out[lab] = ((z.iloc[-1]) ** (1 / yrs) - 1) * 100
            out["mdd" + lab] = (z / z.cummax() - 1).min() * 100
        res.append(out)
    return {k: np.median([r[k] for r in res]) for k in res[0]}


P("## ② 계좌 — 미장 5규칙(N6 제외) 사이트 비중·자리, 한 규칙에만 거르개 · 30시드 중앙"); P("")
P("| 칸 | 연수익 16~ | 낙폭 16~ | 연수익 21~ | 낙폭 21~ | 연수익 23~ | 낙폭 23~ |"); P("|---|---|---|---|---|---|---|")
allm = np.ones(len(SA), bool)
b = acct(allm)
P("| (기준) 거르개 없음 | %+.1f%% | %.1f%% | %+.1f%% | %.1f%% | %+.1f%% | %.1f%% |" % (b["16~"], b["mdd16~"], b["21~"], b["mdd21~"], b["23~"], b["mdd23~"]))
cand = good + [(r, f) for r in ("N1",) for f in ("f8", "f9")] + [("N4", "f7"), ("N1", "f7"), ("N1", "f3"), ("N1", "f2"), ("N2", "f6"), ("N5", "f3"), ("N3", "f1")]
for r, f in cand:
    m = (SA.rid.values != r) | SA[f].values
    x = acct(m)
    P("| [%s]에 %s | %+.1f%% | %.1f%% | %+.1f%% | %.1f%% | %+.1f%% | %.1f%% |" % (NAME[r], FL[f], x["16~"], x["mdd16~"], x["21~"], x["mdd21~"], x["23~"], x["mdd23~"]))

P(""); P("### 대조 — 같은 비율만큼 무작위로 남기기(5번, 각 30시드 중앙의 범위) · 규칙 통째로 빼기"); P("")
P("| 칸 | 연수익 16~ | 연수익 21~ | 연수익 23~ | 낙폭 23~ |"); P("|---|---|---|---|---|")
for r, f in (("N2", "f6"), ("N3", "f1"), ("N4", "f7")):
    fr = SA[SA.rid == r][f].mean()
    xs = []
    for k in range(5):
        rr = np.random.default_rng(100 + k).random(len(SA)) < fr
        xs.append(acct((SA.rid.values != r) | rr))
    rng_ = lambda key: "%+.1f ~ %+.1f%%" % (min(x[key] for x in xs), max(x[key] for x in xs))
    P("| [%s] 무작위 %.0f%%만 남김 | %s | %s | %s | %.1f ~ %.1f%% |" % (NAME[r], fr * 100, rng_("16~"), rng_("21~"), rng_("23~"),
                                                              min(x["mdd23~"] for x in xs), max(x["mdd23~"] for x in xs)))
    x = acct(SA.rid.values != r)
    P("| [%s] 통째로 뺌 | %+.1f%% | %+.1f%% | %+.1f%% | %.1f%% |" % (NAME[r], x["16~"], x["21~"], x["23~"], x["mdd23~"]))
P(""); P("총 %.0f분" % ((time.time() - t0) / 60))
log_trials("us_filter_%s" % time.strftime("%Y%m%d"), 5 * 9)
(ROOT / "reports" / ("us_filter_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")
