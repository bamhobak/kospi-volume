# -*- coding: utf-8 -*-
"""미장 규칙 — **최근 몇 년, 장이 좋아서였나 / 오를 때 덜 먹고 내릴 때 덜 깨지나** (2026-09-29 사용자 요청).

이번 질문은 지수와의 관계 자체라 S&P500·나스닥·유니버스 동일가중과 나란히 잰다(평소 판정 잣대와 다르다).

  ① 미장 계좌(N1~N6, 사이트 비중·자리 그대로) — **매일 평가**(보유 중 평가손익 반영) · 50시드(같은 날 순서 무작위) 중앙
     2021-01 ~ 끝: 연수익·최대낙폭·월 베타·상승 포착률·하락 포착률·연도별·폭락 구간별
  ② 규칙마다 단독 계좌(10자리 × 10%, 20시드) — 같은 지표
  ③ 거래 단위 — 같은 보유 구간 S&P 수익과 짝지어: S&P 가 오른 구간 / 내린 구간의 평균, 기울기(베타)·절편
패널: us_full_2007.pkl(폐지 종목 포함, ~2026-09-22). N6(실적 서프라이즈)은 폐지 종목 실적 자료가 없어 us_scan 생존 종목.
보유가 아직 안 끝난 최근 신호도 넣는다(끝까지 매일 평가) — 안 그러면 2026년 노출이 비어 보인다.
포착률: 상승 포착 = (S&P 상승 달들의 계좌 평균) ÷ (그 달들의 S&P 평균), 하락 포착도 같다. 1보다 작으면 덜 움직였다.

    python research/us_capture.py
"""
import glob, io, sys, time, contextlib, pickle, warnings
warnings.filterwarnings("ignore")
sys.argv = [sys.argv[0], "--panel", "us_full_2007.pkl", "--since", "20160101"]
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
with contextlib.redirect_stdout(io.StringIO()):
    import us_surv_measure as M
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import FinanceDataReader as fdr

T0 = "20210101"
PCT = {"N1": 10, "N2": 5, "N3": 5, "N4": 5, "N5": 5, "N6": 5}
MX = {"N1": 4, "N2": 3, "N3": 3, "N4": 3, "N5": 3, "N6": 3}
HOLD = dict(M.HOLD); HOLD["N6"] = 60
NAME = {"N1": "상승장 신고가", "N2": "낙폭과대", "N3": "저PBR 낙폭", "N4": "자사주 낙폭", "N5": "잔잔한 급등주", "N6": "실적 서프라이즈"}
OUT = []; P = OUT.append; t0 = time.time()


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


K = M.K
ud = np.array(sorted(K.date.unique())); DI = {d: i for i, d in enumerate(ud)}
C = M.rules(pd.Series(True, index=K.index), "u_all")

# 종목별 가격 경로(수정 종가 px) — 매일 평가용
log("가격 경로")
PX = {}
for t, ix in K.groupby("ticker", sort=False).indices.items():
    PX[t] = (K.di.values[ix], K.px.values[ix])


def dedup_all(cond, h, rid):
    Z = K[(cond & (K.buy > 0)).fillna(False)][["date", "ticker", "di", "buy", "cost", "amt20"]].sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(Z.ticker.values, Z.di.values, Z.index):
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h; keep.append(ix)
    Z = Z.loc[keep].copy(); Z["rid"] = rid; Z["hold"] = h
    return Z


log("신호 N1~N5")
SIG = [dedup_all(C[r], HOLD[r], r) for r in ("N1", "N2", "N3", "N4", "N5")]
# N6 — us_drop_n1.py 와 같은 정의(us_scan)
log("신호 N6")
E = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(str(BASE / "data/us/analyst/*.pkl")))], ignore_index=True)
E["dt"] = pd.to_datetime(E["Earnings Date"], utc=True, errors="coerce")
E = E.dropna(subset=["dt", "Surprise(%)"]).copy()
E["edate"] = E.dt.dt.tz_convert("US/Eastern").dt.strftime("%Y%m%d")
E = E.drop_duplicates(["ticker", "edate"], keep="last")
A = pd.read_pickle(BASE / "data/us_scan.pkl")
A = A[((~A.pref.fillna(False)) & (A.rawclose >= 3)).fillna(False)][["ticker", "date", "close", "amt20", "buy", "cost"]]
A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
A["amt_q"] = A.groupby("date").amt20.rank(pct=True)
cal = np.array(sorted(A.date.unique()))
E["bdate"] = [cal[i] if i < len(cal) else None for i in np.searchsorted(cal, E.edate.values, "right")]
E = E.dropna(subset=["bdate"]); E["sur"] = E["Surprise(%)"].astype(float)
E["q"] = E.groupby("bdate").sur.rank(pct=True); E = E[E.groupby("bdate").sur.transform("size") >= 5]
A["peadq"] = (A.ticker + A.date).map(dict(zip(E.ticker + E.bdate, E.q)))
A["ret1"] = (A.close / A.groupby("ticker", sort=False).close.shift(1) - 1) * 100
X = A[((A.amt_q >= 0.6) & (A.peadq >= 0.7) & (A.ret1 >= 3)).fillna(False)]
X = X[(X.buy > 0) & X.date.isin(DI)].sort_values("date")
keep, last = [], {}
for t, d_, ix in zip(X.ticker.values, X.date.values, X.index):
    i = DI[d_]
    if last.get(t, -10 ** 9) >= i:
        continue
    last[t] = i + 60; keep.append(ix)
Y = X.loc[keep]
N6 = pd.DataFrame({"date": Y.date.values, "ticker": Y.ticker.values, "di": [DI[d] for d in Y.date.values],
                   "buy": Y.buy.values, "cost": Y.cost.values, "amt20": Y.amt20.values, "rid": "N6", "hold": 60})
del A, X, Y, E
S = pd.concat(SIG + [N6], ignore_index=True)
S = S[S.date >= "20160101"]
S = S[S.ticker.isin(PX)].reset_index(drop=True)


def path(t, s, h, buy):
    """신호일 s(인덱스) → 보유 1일째(s+1)~청산일(s+h) 종가 ÷ 매수가. 자료 끝이면 거기까지."""
    di, px = PX[t]
    a = np.searchsorted(di, s + 1); b = np.searchsorted(di, s + h, "right")
    return di[a:b], px[a:b] / buy


log("경로 붙이기 %s건" % f"{len(S):,}")
PATH = [path(t, s, h, b) for t, s, h, b in zip(S.ticker.values, S.di.values, S.hold.values, S.buy.values)]
S["ok"] = [len(p[0]) > 0 for p in PATH]
LAST = len(ud) - 1

# ── 기준 지수 ────────────────────────────────────────────────────────
log("지수")
def idx(sym):
    x = fdr.DataReader(sym, "2015-06-01")
    x = x[x.Close > 0]
    return pd.Series(x.Close.values, index=x.index.strftime("%Y%m%d"))
SPX, NDQ = idx("US500"), idx("IXIC")
uq = K.amt20.groupby(K.date).rank(pct=True)
rr = K.px.groupby(K.ticker, sort=False).pct_change().clip(-0.5, 0.5)
liq = (uq.groupby(K.ticker, sort=False).shift(1) >= 0.6).fillna(False)
EW = (1 + rr[liq].groupby(K.date[liq]).mean()).cumprod()          # 유동성 상위 40% 동일가중(매일 재조정)


def sim(Sx, pct, mx, seed, cap=1.0):
    """매일 평가 계좌. 신호일 종가 NAV 로 자리 크기를 정하고 다음날 시가에 산다(비용은 청산 때 차감)."""
    rng = np.random.default_rng(seed)
    by = {}
    for n in range(len(Sx)):
        if Sx.ok.values[n]:
            by.setdefault(Sx.di.values[n], []).append(n)
    cash, pos, navs, inv = 1.0, [], np.empty(len(ud)), np.empty(len(ud))
    cnt = {}
    rid, cost, hold = Sx.rid.values, Sx.cost.values, Sx.hold.values
    for d in range(len(ud)):
        keep, val = [], 0.0
        for p in pos:
            n, alloc, ent = p
            ddi, ratio = PATH_X[n]
            k = np.searchsorted(ddi, d, "right") - 1
            cur = ratio[k] if k >= 0 else 1.0
            if d >= ent + hold[n] or d > ddi[-1]:                     # 보유기간 끝(종가) 또는 자료 끝(폐지 = 마지막 가격)
                cash += alloc * (cur - cost[n] / 100); cnt[rid[n]] -= 1
            else:
                keep.append(p); val += alloc * cur
        pos = keep
        nav = cash + val; navs[d] = nav; inv[d] = val / nav if nav > 0 else 0
        L = by.get(d)
        if not L:
            continue
        L = list(L); rng.shuffle(L)
        for n in L:
            r = rid[n]
            if cnt.get(r, 0) >= mx[r]:
                continue
            a = nav * pct[r] / 100
            if a > cash + 1e-12 or (sum(x[1] for x in pos) + a) > nav * cap + 1e-9:
                continue
            cash -= a; pos.append((n, a, d)); cnt[r] = cnt.get(r, 0) + 1
    return pd.Series(navs, index=ud), pd.Series(inv, index=ud)


def metrics(nav, bench):
    """2021~ 월수익 기준 지표."""
    nav = nav[nav.index >= T0]; b = bench.reindex(nav.index).ffill()
    m = nav.groupby(nav.index.str[:6]).last().pct_change().dropna() * 100
    mb = b.groupby(b.index.str[:6]).last().pct_change().reindex(m.index) * 100
    up, dn = mb > 0, mb < 0
    beta = np.polyfit(mb, m, 1)[0]
    yrs = len(nav) / 252
    return dict(cagr=((nav.iloc[-1] / nav.iloc[0]) ** (1 / yrs) - 1) * 100,
                mdd=(nav / nav.cummax() - 1).min() * 100, beta=beta,
                upc=m[up].mean() / mb[up].mean(), dnc=m[dn].mean() / mb[dn].mean(),
                dnwin=(m[dn] > mb[dn]).mean() * 100, vol=m.std() * np.sqrt(12))


def yearly(nav):
    s = nav[nav.index >= "20201231"]
    y = s.groupby(s.index.str[:4]).last()
    return (y / y.shift(1) - 1).dropna() * 100


EPIS = [("2022 약세장", "20220103", "20221012"), ("2023 가을 조정", "20230731", "20231027"),
        ("2024 8월 급락", "20240716", "20240805"), ("2025 관세 폭락", "20250219", "20250408"),
        ("2025 반등", "20250408", "20250630")]


def episode(nav, a, b):
    s = nav[(nav.index >= a) & (nav.index <= b)]
    return (s.iloc[-1] / s.iloc[0] - 1) * 100 if len(s) > 1 else np.nan


def bench_nav(x):
    x = x[x.index >= "20160101"]
    return x / x.iloc[0]


BN = {"S&P500": bench_nav(SPX), "나스닥": bench_nav(NDQ), "유니버스 동일가중": bench_nav(EW)}

# ── ① 미장 계좌 ─────────────────────────────────────────────────────
log("① 미장 계좌 50시드")
PATH_X = PATH
runs = [sim(S, PCT, MX, s) for s in range(50)]
NAVS = pd.concat([r[0] for r in runs], axis=1); INV = pd.concat([r[1] for r in runs], axis=1)
navm = NAVS.median(axis=1)
pickle.dump({"navs": NAVS, "inv": INV}, open(ROOT / "cache" / "us_capture_acct.pkl", "wb"))
per = [metrics(NAVS[c], SPX) for c in NAVS.columns]
med = {k: np.median([p[k] for p in per]) for k in per[0]}
P("# 미장 규칙 — 최근 5년, 장 덕인가 · 오를 때 덜 먹고 내릴 때 덜 깨지나 · %s" % time.strftime("%Y-%m-%d")); P("")
P("기간 2021-01 ~ %s · 폐지 포함 패널 · 매일 평가 · 계좌는 50시드 중앙. 포착률 1 미만 = S&P 보다 덜 움직임." % ud[-1]); P("")
P("## ① 미장 계좌 (6규칙 · 사이트 비중·자리 그대로) vs 지수"); P("")
P("| 대상 | 연수익 | 최대낙폭 | 월 변동성(연) | 베타(S&P) | 상승 포착 | 하락 포착 | S&P 하락 달에 이긴 비율 | 평균 투입 |")
P("|---|---|---|---|---|---|---|---|---|")
P("| **미장 계좌** | %+.1f%% | %.1f%% | %.1f%% | %.2f | %.2f | %.2f | %.0f%% | %.0f%% |" % (
    med["cagr"], med["mdd"], med["vol"], med["beta"], med["upc"], med["dnc"], med["dnwin"], INV[INV.index >= T0].mean().median() * 100))
for nm, bn in BN.items():
    x = metrics(bn, SPX)
    P("| %s | %+.1f%% | %.1f%% | %.1f%% | %.2f | %.2f | %.2f | %.0f%% | 100%% |" % (nm, x["cagr"], x["mdd"], x["vol"], x["beta"], x["upc"], x["dnc"], x["dnwin"]))
P(""); P("### 연도별 수익"); P("")
ys = yearly(navm); cols = list(ys.index)
P("| 대상 | " + " | ".join(cols) + " |"); P("|---|" + "---|" * len(cols))
P("| **미장 계좌(시드 중앙)** | " + " | ".join("%+.1f%%" % ys[c] for c in cols) + " |")
for nm, bn in BN.items():
    yb = yearly(bn)
    P("| %s | " % nm + " | ".join(("%+.1f%%" % yb[c]) if c in yb else "-" for c in cols) + " |")
P(""); P("### 폭락·반등 구간 (구간 수익)"); P("")
P("| 구간 | 미장 계좌 | S&P500 | 나스닥 | 유니버스 동일가중 | 계좌 평균 투입 |"); P("|---|---|---|---|---|---|")
for nm, a, b in EPIS:
    ex = [episode(NAVS[c], a, b) for c in NAVS.columns]
    iv = INV[(INV.index >= a) & (INV.index <= b)].mean().median() * 100
    P("| %s (%s~%s) | %+.1f%% | %+.1f%% | %+.1f%% | %+.1f%% | %.0f%% |" % (nm, a[2:], b[2:], np.median(ex), episode(BN["S&P500"], a, b),
                                                                 episode(BN["나스닥"], a, b), episode(BN["유니버스 동일가중"], a, b), iv))

# ── ② 규칙마다 단독 계좌 ─────────────────────────────────────────────
P(""); P("## ② 규칙마다 단독 계좌 (최대 10종목 · 종목당 10% · 20시드 중앙) vs S&P500"); P("")
P("| 규칙 | 연수익 | 최대낙폭 | 베타 | 상승 포착 | 하락 포착 | S&P 하락 달에 이긴 비율 | 평균 투입 | 2022 | 2025 관세 폭락 구간 |")
P("|---|---|---|---|---|---|---|---|---|---|")
for r in ("N1", "N2", "N3", "N4", "N5", "N6"):
    log("② %s" % r)
    Sr = S[S.rid == r].reset_index(drop=True)
    PATH_X = [PATH[i] for i in S.index[S.rid == r]]
    rs = [sim(Sr, {r: 10}, {r: 10}, s) for s in range(20)]
    N_ = pd.concat([x[0] for x in rs], axis=1); I_ = pd.concat([x[1] for x in rs], axis=1)
    pm = [metrics(N_[c], SPX) for c in N_.columns]
    md = {k: np.median([p[k] for p in pm]) for k in pm[0]}
    y22 = np.median([episode(N_[c], "20211231", "20221230") for c in N_.columns])
    e25 = np.median([episode(N_[c], "20250219", "20250408") for c in N_.columns])
    P("| [%s] | %+.1f%% | %.1f%% | %.2f | %.2f | %.2f | %.0f%% | %.0f%% | %+.1f%% | %+.1f%% |" % (
        NAME[r], md["cagr"], md["mdd"], md["beta"], md["upc"], md["dnc"], md["dnwin"],
        I_[I_.index >= T0].mean().median() * 100, y22, e25))
P("| (참고) S&P500 | %+.1f%% | %.1f%% | 1.00 | 1.00 | 1.00 | - | 100%% | %+.1f%% | %+.1f%% |" % (
    metrics(BN["S&P500"], SPX)["cagr"], metrics(BN["S&P500"], SPX)["mdd"], episode(BN["S&P500"], "20211231", "20221230"),
    episode(BN["S&P500"], "20250219", "20250408")))

# ── ③ 거래 단위 ──────────────────────────────────────────────────────
P(""); P("## ③ 거래 단위 — 같은 보유 구간의 S&P 수익과 짝지어 (2021~ 진입 · 끝난 거래만)"); P("")
P("| 규칙 | 거래 | 거래 평균 | S&P 같은 구간 평균 | S&P 오른 구간: 거래 / S&P | S&P 내린 구간: 거래 / S&P | 기울기(베타) | 절편(S&P 0일 때 기대) |")
P("|---|---|---|---|---|---|---|---|")
spx_arr = SPX.reindex(ud).ffill().values
for r in ("N1", "N2", "N3", "N4", "N5", "N6"):
    idxs = S.index[(S.rid == r) & (S.date >= T0)]
    tr, sp = [], []
    for n in idxs:
        ddi, ratio = PATH[n]
        s, h = S.di[n], S.hold[n]
        if len(ddi) == 0 or ddi[-1] < s + h:
            continue
        tr.append((ratio[-1] - 1) * 100 - S.cost[n])
        sp.append((spx_arr[s + h] / spx_arr[s] - 1) * 100)
    tr, sp = np.array(tr), np.array(sp)
    if len(tr) < 30:
        continue
    b, a = np.polyfit(sp, tr, 1)
    u, dmask = sp > 0, sp < 0
    P("| [%s] | %s | %+.2f%% | %+.2f%% | %+.2f%% / %+.2f%% | %+.2f%% / %+.2f%% | %.2f | %+.2f%% |" % (
        NAME[r], f"{len(tr):,}", tr.mean(), sp.mean(), tr[u].mean(), sp[u].mean(), tr[dmask].mean(), sp[dmask].mean(), b, a))
P(""); P("총 %.0f분" % ((time.time() - t0) / 60))
rp = ROOT / "reports" / ("us_capture_%s.md" % time.strftime("%Y%m%d"))
rp.write_text("\n".join(OUT) + "\n", encoding="utf-8")
print("\n".join(OUT))
