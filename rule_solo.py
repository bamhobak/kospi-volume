# -*- coding: utf-8 -*-
"""규칙 15개를 **하나씩 따로** 잰다 — 지수·다른 규칙과 비교하지 않는다 (2026-09-23 사용자 요청).

"모든 규칙 실측 테스트 다시 한번 해보자, 지수랑도 비교하지 말고 각각 별개로 각자 진행했을 때
 기준으로 해줘, 다른 규칙들과 비교하지 말고"

그래서 각 규칙의 **절대 성적**만 본다. 두 가지 잣대:

  ① 건별 — 신호가 나면 다 산다고 본다('돈 무한' 전제, [[rule-test-unconstrained]]).
     건수 · 신호 난 달 · 평균 · 중앙 · 승률 · PF · 손익비 · 최악 · 상위5% 뺀 평균 · 연도별.
  ② 단독 계좌 — **그 규칙 하나에 돈을 전부 맡겼을 때.** 모든 규칙을 **같은 틀**로 돌린다:
     최대 10종목 · 종목당 계좌의 10%. (규칙별 자리 수 mx 는 여러 규칙을 섞는 계좌에 맞춘 값이라
     단독으로 쓰면 자리 3개짜리는 한 종목에 33% 가 몰려 낙폭이 규칙이 아니라 설정 때문에 커진다.)
     매일 종가로 평가(낙폭을 청산 때만 재면 작게 나온다), 같은 날 신호가 자리보다 많으면
     무작위로 고른다(티커 순 우선은 착시였다 [[tiebreak-trail]]) — 30시드 중앙값.

기간: 2016~ (학습 2016~22 · 검증 2023~26). 국내는 2005~15 를 참고로 건별만 덧붙인다.
미장 2016 이전은 생존편향 때문에 재지 않는다([[kr-holdout-2005-2015]]).
⚠ 미장 신호는 data/sector_drop_us_sig.pkl(2026-09-15 캐시)과 사이트 정의로 만든 N6 이다.

    python rule_solo.py            # 전부
    python rule_solo.py P1 N6      # 골라서
"""
import glob, io, os, pickle, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
SINCE, VA0 = "20160101", "20230101"
SEEDS = 30
SLOTS = 10            # 단독 계좌: 최대 10종목 · 종목당 10% (모든 규칙 같은 틀)
PICK = set(a for a in sys.argv[1:] if not a.startswith("-"))
t0 = time.time()


def log(m):
    print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


# 사이트 화면 이름(사용자 순서)으로 부른다 — 내부 id 와 다르다([[rule-naming-talk]])
NAME = {"P7": "외인 매집", "P1": "조용한 신고가", "P4": "업종붕괴 이탈", "P6": "깊은 이격",
        "P3": "폭락반등", "P2": "조정매집", "D1": "낙폭과대(코스닥)", "D2": "저PBR 낙폭(코스닥)",
        "P5": "자사주 낙폭(국내)", "N1": "상승장 신고가", "N2": "낙폭과대(미장)",
        "N3": "저PBR 낙폭(미장)", "N4": "자사주 낙폭(미장)", "N5": "잔잔한 급등주",
        "N6": "실적 서프라이즈"}
ORDER = ["P7", "P1", "P2", "P3", "P4", "P6", "P5", "D1", "D2", "N1", "N2", "N3", "N4", "N5", "N6"]


# ── 거래 목록 + 가격 경로 ────────────────────────────────────────────
class Book:
    """한 규칙의 거래 목록(di·hold·ret)과, 매일 평가에 쓸 가격 행렬(날짜×종목)."""

    def __init__(self, rid, T, dates, P, tix, mx, hold):
        self.rid, self.T, self.dates, self.P, self.tix, self.mx, self.hold = rid, T, dates, P, tix, mx, hold


def wide(K, col):
    dates = np.array(sorted(K.date.unique()))
    tick = np.array(sorted(K.ticker.unique()))
    di = np.searchsorted(dates, K.date.values)
    ti = np.searchsorted(tick, K.ticker.values)
    P = np.full((len(dates), len(tick)), np.nan, dtype=np.float32)
    P[di, ti] = K[col].values.astype(np.float32)
    return dates, {t: i for i, t in enumerate(tick)}, P


def dedupe(X, hold):
    """같은 종목이 보유 중에 또 걸리면 버린다(한 종목 한 자리)."""
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + hold
        keep.append(ix)
    return X.loc[keep]


books = {}

# 국내 — portfolio.py 의 규칙 정의를 그대로 쓴다(stats_2016.py 와 같은 방식)
if not PICK or PICK & {"P1", "P2", "P3", "P4", "P5", "P6", "P7", "D1", "D2"}:
    log("국내 패널·규칙 읽는 중 (portfolio.py)")
    src = (BASE / "portfolio.py").read_text(encoding="utf-8")
    ns = {"__file__": str(BASE / "portfolio.py")}
    real = sys.stdout
    sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
    sys.stdout = real
    assert not ns["TRAIL"], "트레일이 켜져 있다 — 이 도구는 '정해진 날까지 보유' 만 잰다"
    cache = {}
    for rid, (K, hold, stop, pct, mx, cond) in ns["RULES"].items():
        if PICK and rid not in PICK:
            continue
        key = id(K)
        if key not in cache:
            cache[key] = wide(K, "close")    # 국내 n{h} 는 close 기준(build_panel.py)
        dates, tix, P = cache[key]
        m = cond.fillna(False).values
        X = K[m][["ticker", "date", "buy", f"n{hold}"]].rename(columns={f"n{hold}": "ret"})
        X = X.replace([np.inf, -np.inf], np.nan).dropna(subset=["ret"])
        X = X[X.buy > 0]
        X["di"] = np.searchsorted(dates, X.date.values)
        X = X[X.di + hold + 1 <= len(dates) - 1].sort_values("di")    # 덜 끝난 거래는 뺀다
        X = dedupe(X, hold)
        books[rid] = Book(rid, X.reset_index(drop=True), dates, P, tix, mx, hold)
        log(f"  {rid} {NAME[rid]} {len(X):,}건 · 보유 {hold}일 · 자리 {mx}")

# 미장 — N1~N5 는 캐시, N6 은 사이트 정의로 만든다(us_drop_n1.py 와 같은 코드)
if not PICK or PICK & {"N1", "N2", "N3", "N4", "N5", "N6"}:
    log("미장 패널 읽는 중 (us_scan.pkl)")
    A = pd.read_pickle(BASE / "data/us_scan.pkl")
    A = A[((~A.pref.fillna(False)) & (A.rawclose >= 3)).fillna(False)]
    A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
    udates, utix, UP = wide(A[A.date >= "20150101"], "close")
    with open(BASE / "data" / "sector_drop_us_sig.pkl", "rb") as f:
        C = pickle.load(f)
    S = C["S"]
    MXU = S.groupby("rid").mx.first().to_dict()
    HLU = S.groupby("rid").hold.first().to_dict()
    # N6 — 실적 서프라이즈 상위 30% · 발표 다음 거래일 +3% · 거래대금 상위 40% · 60일
    E = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(str(BASE / "data/us/analyst/*.pkl")))],
                  ignore_index=True)
    E["dt"] = pd.to_datetime(E["Earnings Date"], utc=True, errors="coerce")
    E = E.dropna(subset=["dt", "Surprise(%)"]).copy()
    E["edate"] = E.dt.dt.tz_convert("US/Eastern").dt.strftime("%Y%m%d")
    E = E.drop_duplicates(["ticker", "edate"], keep="last")
    A["amt_q"] = A.groupby("date").amt20.rank(pct=True)
    cal = np.array(sorted(A.date.unique()))
    E["bdate"] = [cal[i] if i < len(cal) else None for i in np.searchsorted(cal, E.edate.values, "right")]
    E = E.dropna(subset=["bdate"])
    E["sur"] = E["Surprise(%)"].astype(float)
    E["q"] = E.groupby("bdate").sur.rank(pct=True)
    E = E[E.groupby("bdate").sur.transform("size") >= 5]
    A["peadq"] = (A.ticker + A.date).map(dict(zip(E.ticker + E.bdate, E.q)))
    A["ret1"] = (A.close / A.groupby("ticker", sort=False).close.shift(1) - 1) * 100
    c6 = ((A.amt_q >= 0.6) & (A.peadq >= 0.7) & (A.ret1 >= 3)).fillna(False)
    X6 = A[c6][["ticker", "date", "buy", "n60"]].rename(columns={"n60": "ret"}).assign(rid="N6")
    MXU["N6"], HLU["N6"] = 3, 60
    SU = pd.concat([S[["ticker", "date", "rid", "ret"]].merge(
        A[["ticker", "date", "buy"]], on=["ticker", "date"], how="left"), X6], ignore_index=True)
    del A, E
    for rid in ["N1", "N2", "N3", "N4", "N5", "N6"]:
        if PICK and rid not in PICK:
            continue
        hold, mx = int(HLU[rid]), int(MXU[rid])
        X = SU[(SU.rid == rid) & (SU.date >= "20150101")].copy()
        X = X.replace([np.inf, -np.inf], np.nan).dropna(subset=["ret", "buy"])
        X = X[X.buy > 0]
        X["di"] = np.searchsorted(udates, X.date.values)
        X = X[X.di + hold + 1 <= len(udates) - 1].sort_values("di")
        X = dedupe(X, hold)
        books[rid] = Book(rid, X.reset_index(drop=True), udates, UP, utix, mx, hold)
        log(f"  {rid} {NAME[rid]} {len(X):,}건 · 보유 {hold}일 · 자리 {mx}")


# ── ① 건별 ──────────────────────────────────────────────────────────
def pf(z):
    up, dn = z[z > 0].sum(), -z[z < 0].sum()
    return up / dn if dn > 0 else float("inf")


def trade_stats(z, lo, hi):
    z = z[(z.date >= lo) & (z.date <= hi)]
    r = z.ret.astype(float)
    if not len(r):
        return None
    w, l = r[r > 0], r[r <= 0]
    mo = z.date.str[:6]
    span = (int(hi[:4]) * 12 + int(hi[4:6]) if hi < "20991231" else 2026 * 12 + 9) - (int(lo[:4]) * 12 + int(lo[4:6])) + 1
    return dict(n=len(r), mon=mo.nunique(), span=span, avg=r.mean(), med=r.median(),
                win=(r > 0).mean() * 100, pf=pf(r),
                payoff=(w.mean() / -l.mean()) if len(w) and len(l) and l.mean() < 0 else float("nan"),
                worst=r.min(), trim=r[r <= r.quantile(0.95)].mean())


# ── ② 단독 계좌 (매일 평가) ─────────────────────────────────────────
def solo(b, seed):
    rng = np.random.default_rng(seed)
    T = b.T[b.T.date >= SINCE]
    d0 = int(np.searchsorted(b.dates, SINCE))
    dN = len(b.dates) - 1
    byd = {k: g for k, g in T.groupby("di")}
    cash, pos = 1.0, []          # pos: (exit_di, ti, buy, alloc, ret)
    navs, inv = [], []
    for d in range(d0, dN + 1):
        # 오늘 종가 기준 평가 · 청산
        keep = []
        for p in pos:
            ex, ti, buy, alloc, ret, ent = p
            if d >= ex:
                cash += alloc * (1 + ret / 100)
            else:
                keep.append(p)
        pos = keep
        val = 0.0
        for ex, ti, buy, alloc, ret, ent in pos:
            px = b.P[d, ti]
            val += alloc * (px / buy if np.isfinite(px) and px > 0 else 1.0)
        nav = cash + val
        navs.append(nav)
        inv.append(val / nav if nav > 0 else 0)
        # 어제(d-1) 신호 → 오늘 시가 진입이지만, 오늘 종가 평가는 위에서 이미 했으므로
        # 오늘 신호는 내일 시가에 들어간다고 보고 여기서 자리만 잡는다(다음 날 평가부터 반영).
        g = byd.get(d)
        if g is None:
            continue
        free = SLOTS - len(pos)
        if free <= 0:
            continue
        held = {p[1] for p in pos}
        g = g.sample(frac=1, random_state=int(rng.integers(1 << 30)))
        for r in g.itertuples():
            if free <= 0:
                break
            ti = b.tix.get(r.ticker)
            if ti is None or ti in held:
                continue
            alloc = min(nav / SLOTS, cash)
            if alloc <= nav * 0.01:
                break
            cash -= alloc
            pos.append((d + b.hold, ti, float(r.buy), alloc, float(r.ret), d))
            held.add(ti)
            free -= 1
    nav = np.array(navs)
    dd = nav / np.maximum.accumulate(nav) - 1
    yrs = (dN - d0 + 1) / 252
    # 언더워터: 전고점을 다시 넘기까지 걸린 가장 긴 기간
    peak_i, long_uw = 0, 0
    run_max = -1
    for i, v in enumerate(nav):
        if v >= run_max:
            run_max = v
            peak_i = i
        else:
            long_uw = max(long_uw, i - peak_i)
    ydates = b.dates[d0:dN + 1]
    s = pd.Series(nav, index=[x[:4] for x in ydates])
    yend = s.groupby(level=0).last()
    ystart = pd.concat([pd.Series([1.0], index=["_"]), yend]).shift(1).iloc[1:]
    yret = (yend / ystart.values - 1) * 100
    return dict(mult=nav[-1], cagr=(nav[-1] ** (1 / yrs) - 1) * 100, mdd=dd.min() * 100,
                expo=float(np.mean(inv)) * 100, uw=long_uw / 252, yret=yret)


# ── 실행 ────────────────────────────────────────────────────────────
PER = [("학습 2016~22", "20160101", "20221231"), ("검증 2023~26", VA0, "20991231"),
       ("전체 2016~", SINCE, "20991231")]
RES = {}
for rid in ORDER:
    if rid not in books:
        continue
    b = books[rid]
    log(f"{rid} {NAME[rid]} 단독 계좌 {SEEDS}시드")
    runs = [solo(b, s) for s in range(SEEDS)]
    RES[rid] = dict(
        tr={pn: trade_stats(b.T, lo, hi) for pn, lo, hi in PER},
        stress=trade_stats(b.T, "20050101", "20151231") if rid[0] in "PD" else None,
        yr={y: (len(g), g.ret.mean(), (g.ret > 0).mean() * 100) for y, g in
            b.T[b.T.date >= SINCE].groupby(b.T.date.str[:4])},
        acct={k: float(np.median([r[k] for r in runs])) for k in ("mult", "cagr", "mdd", "expo", "uw")},
        acct_lo={k: float(np.percentile([r[k] for r in runs], 10)) for k in ("mult", "cagr")},
        acct_mdd_worst=float(np.min([r["mdd"] for r in runs])),
        yret=pd.concat([r["yret"] for r in runs], axis=1).median(axis=1),
        hold=b.hold, mx=b.mx)

# ── 보고 ────────────────────────────────────────────────────────────
f = lambda v, p="%+.2f%%": (p % v) if v == v and v not in (float("inf"),) else "—"
print("\n## ① 건별 — 신호 나면 다 산다 (2016~ 전체)\n")
print("| 규칙 | 보유 | 건수 | 신호 난 달 | 평균 | 중앙 | 승률 | PF | 손익비 | 상위5% 뺀 평균 | 최악 |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for rid, R in RES.items():
    z = R["tr"]["전체 2016~"]
    if not z:
        print(f"| [{NAME[rid]}] | {R['hold']}일 | 0 | — | — | — | — | — | — | — | — |"); continue
    print(f"| [{NAME[rid]}] | {R['hold']}일 | {z['n']:,} | {z['mon']}/{z['span']} | {f(z['avg'])} | {f(z['med'])} | "
          f"{z['win']:.0f}% | {z['pf']:.2f} | {z['payoff']:.2f} | {f(z['trim'])} | {z['worst']:+.1f}% |")

print("\n## ① 건별 — 학습 vs 검증 (같은 규칙이 뒤쪽에서도 버티나)\n")
print("| 규칙 | 학습 16~22 건수 | 평균 | 승률 | PF | 검증 23~26 건수 | 평균 | 승률 | PF | 국내 05~15(참고) 평균 · 승률 · PF |")
print("|---|---|---|---|---|---|---|---|---|---|")
for rid, R in RES.items():
    a, v, s = R["tr"]["학습 2016~22"], R["tr"]["검증 2023~26"], R["stress"]
    A_ = f"{a['n']:,} | {f(a['avg'])} | {a['win']:.0f}% | {a['pf']:.2f}" if a else "0 | — | — | —"
    V_ = f"{v['n']:,} | {f(v['avg'])} | {v['win']:.0f}% | {v['pf']:.2f}" if v else "0 | — | — | —"
    S_ = f"{f(s['avg'])} · {s['win']:.0f}% · {s['pf']:.2f} ({s['n']:,}건)" if s else "—"
    print(f"| [{NAME[rid]}] | {A_} | {V_} | {S_} |")

print("\n## ② 단독 계좌 — 그 규칙 하나에 돈 전부 (2016~, 최대 10종목 · 종목당 10% · 매일 평가 · 30시드 중앙)\n")
print("| 규칙 | 보유 | 최종 배수 | 연수익 | 연수익(하위10%) | 최대낙폭 | 최악 시드 낙폭 | 평균 투입률 | 최장 제자리 |")
print("|---|---|---|---|---|---|---|---|---|")
for rid, R in RES.items():
    a = R["acct"]
    print(f"| [{NAME[rid]}] | {R['hold']}일 | {a['mult']:.2f}배 | {a['cagr']:+.1f}% | {R['acct_lo']['cagr']:+.1f}% | "
          f"{a['mdd']:.1f}% | {R['acct_mdd_worst']:.1f}% | {a['expo']:.0f}% | {a['uw']:.1f}년 |")

print("\n## ② 단독 계좌 — 연도별 수익 (30시드 중앙)\n")
ys = sorted({y for R in RES.values() for y in R["yret"].index})
print("| 규칙 | " + " | ".join(ys) + " | 손실 난 해 |")
print("|---|" + "---|" * (len(ys) + 1))
for rid, R in RES.items():
    yr = R["yret"]
    cells = [f"{yr[y]:+.0f}%" if y in yr.index and yr[y] == yr[y] else "·" for y in ys]
    neg = sum(1 for y in ys if y in yr.index and yr[y] < 0)
    print(f"| [{NAME[rid]}] | " + " | ".join(cells) + f" | {neg}/{len(yr)} |")

print("\n## ① 건별 — 연도별 평균 (건수)\n")
print("| 규칙 | " + " | ".join(ys) + " |")
print("|---|" + "---|" * len(ys))
for rid, R in RES.items():
    cells = [f"{R['yr'][y][1]:+.1f}% ({R['yr'][y][0]})" if y in R["yr"] else "·" for y in ys]
    print(f"| [{NAME[rid]}] | " + " | ".join(cells) + " |")

log(f"끝 ({(time.time() - t0) / 60:.1f}분)")
