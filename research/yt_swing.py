# -*- coding: utf-8 -*-
"""유튜브 스윙 기법 다섯 편 실측 (2026-09-30, 사용자가 링크 5개 보냄).

  A 부자회사원 · 올리버 벨레즈 '스윙 트레이딩 바이블' 원조 타점
      매달 1~15일 누적 상승률 상위 2종목(시총 500억↑·신규상장 제외) → 고점 뒤 **고가가 낮아지는 음봉 3개 이상**
      → 다음날 그 캔들 고가를 넘으면 매수, 손절 = 그 캔들 저가, 손익비 1:2 에서 절반·1:3 에서 나머지,
      1:2 를 넘은 뒤 1:2 로 돌아오면 나머지도 매도. 돌파 안 나오면 음봉을 다시 센다. (영상 자체 검증 = 3달·6종목)
      A2 넓힌 판: 10일 +40% 이상 오른 종목 전부(같은 종목 40일 안 재등장 제외)
  B 주덕 · 기간조정 스윙: 60일 고점 근처를 3번 이상 터치 + 저점이 20일마다 높아짐 + 하락일 거래량 < 상승일 거래량
      + 20일선 상승·60일선 위. 고점 돌파 전(고점 -5% 안)과 돌파일 두 판.
  C 창원개미TV · 오래 다진 자리의 신고가: 120일 고가 돌파 + 앞 40일 종가가 그 고가 -15% 안에서 머묾 + 20일 상승 20% 이하
      (수직 상승 제외). 목표 +7% · 5일 안, 아니면 5일째 종가, 손절 = 종가가 다진 자리 저점 아래.
  D 시윤주식 · '발만 담그고 바닥 확인 뒤 사라': 우리 국내 규칙 신호에 진입만 바꿔 본다(같은 40일 끝날 기준)
      즉시 100% / 10% 먼저 + 바닥 확인(종가 > 전일 고가, 또는 아래꼬리 ≥ 몸통 2배) 뒤 90% / 확인 뒤 100%.
  검은사월(코인 레인지·N 패턴 단타·R 2%)은 일봉 규칙이 아니라 뺐다.

    python research/yt_swing.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
import run_spec as R
from verdict import log_trials

OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
PER = [("옛날 05~15", "20050101", "20151231"), ("학습 16~22", "20160101", "20221231"), ("검증 23~", "20230101", "20991231")]


def per_of(d):
    return 0 if d <= "20151231" else (1 if d <= "20221231" else 2)


def stats_row(lab, r, d):
    r = np.asarray(r, float); d = np.asarray(d)
    cells = [lab, f"{len(r):,}"]
    for i in range(3):
        m = np.array([per_of(x) == i for x in d]) if len(d) else np.array([], bool)
        w = r[m] if len(r) else r
        cells.append("%+.2f / %+.2f · %.0f%%" % (np.median(w), w.mean(), (w > 0).mean() * 100) if len(w) >= 20 else ("n=%d" % len(w)))
    ys = pd.Series(r).groupby(pd.Series(d).str[:4]).mean() if len(r) else pd.Series(dtype=float)
    cells.append("%d/%d" % ((ys > 0).sum(), len(ys)))
    P("| " + " | ".join(cells) + " |")


def stats_head():
    P("| 판 | 거래 | 옛날 05~15 중앙/평균·승률 | 학습 16~22 | 검증 23~ | 평균 양수 해 |"); P("|---|---|---|---|---|---|")


# ── 공통 패널 ──────────────────────────────────────────────────────────────────
def load():
    A, uni, since = R.load_market("KR")
    A["uni"] = uni.values
    A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
    A["age"] = A.groupby("ticker").cumcount()
    A["pref"] = A.ticker.astype(str).str[-1] != "0"
    return A


def arrays(A):
    T = {}
    for t, g in A.groupby("ticker", sort=False):
        T[t] = dict(i0=g.index[0], d=g.date.values, o=g.open.values.astype(float), h=g.high.values.astype(float),
                    l=g.low.values.astype(float), c=g.close.values.astype(float), v=g.volume.values.astype(float),
                    cost=g.cost.values.astype(float))
    return T


# ── A 벨레즈 ───────────────────────────────────────────────────────────────────
def velez_trade(x, s, maxwait=40, maxhold=60, mode="rr"):
    o, h, l, c = x["o"], x["h"], x["l"], x["c"]; n = len(c)
    run = 0
    for j in range(s + 1, min(n - 1, s + maxwait)):
        bear = c[j] < o[j]
        if bear and run > 0 and h[j] < h[j - 1]:
            run += 1
        elif bear:
            run = 1
        else:
            run = 0
        if run >= 3:
            k = j + 1; trig = h[j]
            if h[k] > trig:
                entry = max(o[k], trig); stop = l[j]
                if entry <= stop or not np.isfinite(entry):
                    return None
                Rr = entry - stop; t1 = entry + 2 * Rr; t2 = entry + 3 * Rr
                half = False; got = 0.0
                for d in range(k, min(n, k + maxhold)):
                    if mode == "hold20":
                        if l[d] <= stop and d > k or (d == k and c[d] <= stop):
                            px = min(o[d], stop) if d > k else stop
                            return x["d"][k], (px / entry - 1) * 100 - x["cost"][k], d - k
                        if d - k >= 19:
                            return x["d"][k], (c[d] / entry - 1) * 100 - x["cost"][k], d - k
                        continue
                    if not half:
                        if (d > k and l[d] <= stop) or (d == k and c[d] <= stop):
                            px = min(o[d], stop) if d > k else stop
                            return x["d"][k], (px / entry - 1) * 100 - x["cost"][k], d - k
                        if h[d] >= t1:
                            half = True; got = 0.5 * (max(o[d], t1) / entry - 1) * 100 if d > k else 0.5 * (t1 / entry - 1) * 100
                            if h[d] >= t2:
                                return x["d"][k], got + 0.5 * (t2 / entry - 1) * 100 - x["cost"][k], d - k
                            continue
                    else:
                        if l[d] <= t1:
                            return x["d"][k], got + 0.5 * (min(o[d], t1) / entry - 1) * 100 - x["cost"][k], d - k
                        if h[d] >= t2:
                            return x["d"][k], got + 0.5 * (max(o[d], t2) / entry - 1) * 100 - x["cost"][k], d - k
                last = min(n, k + maxhold) - 1
                rest = (c[last] / entry - 1) * 100
                return x["d"][k], (got + 0.5 * rest if half else rest) - x["cost"][k], last - k
            run = 0          # 돌파 안 나오면 다시 센다
    return None


def part_a(A, T):
    P(""); P("## A 벨레즈 원조 타점(부자회사원)"); P("")
    # 정확판: 매달 1~15일 상승률 상위 2
    A["ym"] = A.date.str[:6]; A["dd"] = A.date.str[6:8].astype(int)
    last_prev = A.groupby(["ticker", "ym"]).close.last().groupby(level=0).shift(1)
    mid = A[A.dd <= 15].groupby(["ticker", "ym"]).agg(c15=("close", "last"), idx=("close", lambda s: s.index[-1]),
                                                       mc=("marcap", "last"), age=("age", "last"), pref=("pref", "last"))
    mid["base"] = last_prev.reindex(mid.index)
    mid["r"] = mid.c15 / mid.base - 1
    mid = mid[(mid.mc >= 5e10) & (mid.age >= 60) & ~mid.pref].dropna(subset=["r"])
    top2 = mid.sort_values("r", ascending=False).groupby(level="ym").head(2)
    ev_exact = [(t, int(ix)) for (t, ym), ix in zip(top2.index, top2.idx)]
    # 넓힌 판: 10일 +40% 이상
    A["r10"] = A.groupby("ticker").close.pct_change(10)
    cand = A[(A.r10 >= 0.4) & (A.marcap >= 5e10) & (A.age >= 120) & ~A.pref]
    ev_broad = []; lastev = {}
    for t, ix in zip(cand.ticker.values, cand.index.values):
        if t in lastev and ix - lastev[t] < 40:
            continue
        lastev[t] = ix; ev_broad.append((t, int(ix)))
    stats_head()
    for lab, evs in (("A 정확판 매달 상위 2", ev_exact), ("A2 넓힌 판 10일 +40%", ev_broad)):
        for mode, ml in (("rr", "손익비 1:2·1:3"), ("hold20", "손절만·20일 보유")):
            rs, ds, hs = [], [], []
            for t, ix in evs:
                x = T[t]; s = ix - x["i0"]
                tr = velez_trade(x, s, mode=mode)
                if tr:
                    ds.append(tr[0]); rs.append(tr[1]); hs.append(tr[2])
            stats_row("%s · %s (평균 %.0f일)" % (lab, ml, np.mean(hs) if hs else 0), rs, ds)
        # 타점 없이: 선정 다음날 시가에 사서 20일
        rs, ds = [], []
        for t, ix in evs:
            x = T[t]; s = ix - x["i0"]
            if s + 21 < len(x["c"]):
                rs.append((x["c"][s + 20] / x["o"][s + 1] - 1) * 100 - x["cost"][s + 1]); ds.append(x["d"][s + 1])
        stats_row("%s · 타점 없이 다음날 사서 20일(비교)" % lab, rs, ds)
    P(""); P("중앙/평균은 거래 1건 수익(%, 비용 차감). 음봉 3개 조건이 40일 안에 안 나오면 거래 없음.")


# ── B 기간조정 ────────────────────────────────────────────────────────────────
def part_b(A, T):
    from numpy.lib.stride_tricks import sliding_window_view as sw
    rows = []
    for t, x in T.items():
        n = len(x["c"])
        if n < 130:
            continue
        h, l, c, v = x["h"], x["l"], x["c"], x["v"]
        H = sw(h, 60); L = sw(l, 60)                       # 창 끝 = 오늘
        idx = np.arange(59, n)
        h60 = H.max(1)
        touch = (H >= 0.97 * h60[:, None]).sum(1)
        first = np.argmax(H >= 0.97 * h60[:, None], axis=1); lastt = 59 - np.argmax((H >= 0.97 * h60[:, None])[:, ::-1], axis=1)
        low3 = L[:, 40:].min(1); low2 = L[:, 20:40].min(1); low1 = L[:, :20].min(1)
        cc = pd.Series(c); ma20 = cc.rolling(20).mean().values; ma60 = cc.rolling(60).mean().values
        up = np.r_[False, c[1:] > c[:-1]]; dn = np.r_[False, c[1:] < c[:-1]]
        vu = pd.Series(np.where(up, v, np.nan)).rolling(20, min_periods=5).mean().values
        vd = pd.Series(np.where(dn, v, np.nan)).rolling(20, min_periods=5).mean().values
        prevh = np.r_[np.nan, h60[:-1]]                       # 어제까지의 60일 고가
        base = (touch >= 3) & (lastt - first >= 15) & (low3 > low2) & (low2 > low1) \
            & (vd[idx] < 0.8 * vu[idx]) & (ma20[idx] > ma60[idx]) & (ma20[idx] > np.r_[np.full(5, np.nan), ma20[:-5]][idx])
        near = base & (c[idx] >= 0.95 * h60) & (c[idx] < h60)
        brk = base & (c[idx] > prevh)
        for m, lab in ((near, "B 돌파 전(고점 -5% 안)"), (brk, "B 돌파일")):
            for k in np.where(m)[0]:
                rows.append((lab, t, x["d"][idx[k]]))
    E = pd.DataFrame(rows, columns=["lab", "ticker", "date"])
    E = E.sort_values(["lab", "ticker", "date"])
    E["di"] = E.groupby(["lab", "ticker"]).date.transform(lambda s: pd.to_datetime(s).diff().dt.days)
    E = E[E.di.isna() | (E.di > 30)]                       # 같은 종목 한 달 안 재신호 제외
    U = A[["ticker", "date", "n20", "n40", "uni"]].copy()
    U["m20"] = U.groupby("date").n20.transform("median"); U["m40"] = U.groupby("date").n40.transform("median")
    E = E.merge(U, on=["ticker", "date"], how="left")
    P(""); P("## B 기간조정 스윙(주덕) — 다음날 시가 매수 · 비용 차감"); P("")
    P("| 판 | 신호 | 기간 | 20일 중앙 | 40일 중앙 | 40일 평균 | 40일 승률 | 40일 같은 날 대비 | 40일 양수 해 |"); P("|---|---|---|---|---|---|---|---|---|")
    for lab, g in E.groupby("lab"):
        g = g.dropna(subset=["n40"])
        for i, (pl, a, b) in enumerate(PER):
            z = g[(g.date >= a) & (g.date <= b)]
            if len(z) < 20:
                continue
            ys = z.groupby(z.date.str[:4]).n40.mean()
            P("| %s | %d | %s | %+.2f | %+.2f | %+.2f | %.0f%% | %+.2f | %d/%d |" % (lab, len(z), pl, z.n20.median(), z.n40.median(), z.n40.mean(),
                                                                            (z.n40 > 0).mean() * 100, (z.n40 - z.m40).median(), (ys > 0).sum(), len(ys)))


# ── C 다진 자리 신고가 ─────────────────────────────────────────────────────────
def part_c(A, T):
    rows = []
    for t, x in T.items():
        n = len(x["c"])
        if n < 200:
            continue
        o, h, l, c = x["o"], x["h"], x["l"], x["c"]
        ph = pd.Series(h).shift(1).rolling(120).max().values
        mc40 = pd.Series(c).shift(1).rolling(40).min().values
        ml40 = pd.Series(l).shift(1).rolling(40).min().values
        r20 = np.r_[np.full(20, np.nan), c[20:] / c[:-20] - 1] * 100
        sig = (c > ph) & (mc40 >= 0.85 * ph) & (r20 <= 20)
        lastk = -99
        for k in np.where(sig)[0]:
            if k - lastk < 20 or k + 25 >= n:
                continue
            lastk = k
            e = o[k + 1]; tgt = e * 1.07; stop = ml40[k]; res = None
            for d in range(k + 1, k + 6):
                if h[d] >= tgt:
                    res = (max(o[d], tgt) / e - 1) * 100 if d > k + 1 else (tgt / e - 1) * 100; break
                if c[d] < stop:
                    res = (c[d] / e - 1) * 100; break
            if res is None:
                res = (c[k + 5] / e - 1) * 100
            rows.append((x["d"][k], res - x["cost"][k + 1], (c[k + 20] / e - 1) * 100 - x["cost"][k + 1]))
    E = pd.DataFrame(rows, columns=["date", "r5", "r20"])
    P(""); P("## C 오래 다진 자리의 신고가(창원개미TV)"); P("")
    stats_head()
    stats_row("C 목표 +7%·5일", E.r5.values, E.date.values)
    stats_row("C 그냥 20일 보유", E.r20.values, E.date.values)


# ── D 우리 규칙 신호 진입 바꾸기 ────────────────────────────────────────────────
def part_d(A, T):
    import rule_scan as RS
    S = RS.kr_signals()[["date", "ticker", "rid"]]
    didx = {}
    for t, x in T.items():
        didx[t] = {d: i for i, d in enumerate(x["d"])}
    res = []
    for d0, t, rid in S.itertuples(index=False):
        x = T.get(t)
        if x is None or d0 not in didx[t]:
            continue
        s = didx[t][d0]; n = len(x["c"])
        if s + 41 >= n:
            continue
        o, h, l, c = x["o"], x["h"], x["l"], x["c"]
        end = c[s + 40]; cost = x["cost"][s + 1]
        e0 = o[s + 1]
        conf = None
        for j in range(s + 1, s + 11):
            body = abs(c[j] - o[j]); lw = min(o[j], c[j]) - l[j]
            if c[j] > h[j - 1] or (body > 0 and lw >= 2 * body):
                conf = j; break
        e1 = o[conf + 1] if conf is not None else c[s + 10]
        r_now = (end / e0 - 1) * 100 - cost
        r_conf = (end / e1 - 1) * 100 - cost
        r_mix = 0.1 * (end / e0 - 1) * 100 + 0.9 * (end / e1 - 1) * 100 - cost
        res.append((d0, rid, r_now, r_conf, r_mix, conf is not None, (e1 / e0 - 1) * 100))
    E = pd.DataFrame(res, columns=["date", "rid", "now", "conf", "mix", "hasconf", "slip"])
    P(""); P("## D 발만 담그고 바닥 확인 뒤 사기(시윤주식) — 우리 국내 규칙 신호 %s건 · 신호 뒤 40거래일째 종가 기준" % f"{len(E):,}"); P("")
    P("바닥 확인 = 10일 안에 종가 > 전일 고가 또는 아래꼬리 ≥ 몸통 2배 → 다음날 시가(없으면 10일째 종가). 확인까지 기다린 신호 %.0f%% · 진입가 차이 중앙 %+.2f%%" % (
        E.hasconf.mean() * 100, E.slip.median()))
    P(""); stats_head()
    stats_row("즉시 100%", E.now.values, E.date.values)
    stats_row("10% 먼저 + 확인 뒤 90%", E.mix.values, E.date.values)
    stats_row("확인 뒤 100%", E.conf.values, E.date.values)
    P(""); P("| 규칙 | 신호 | 즉시 평균 | 10%+90% 평균 | 확인 뒤 평균 |"); P("|---|---|---|---|---|")
    for rid, g in E.groupby("rid"):
        P("| %s | %d | %+.2f | %+.2f | %+.2f |" % (rid, len(g), g.now.mean(), g.mix.mean(), g.conf.mean()))


# ── E 앨런 팔리 '사악한 기획'(부자회사원 · 리노 ABC) ──────────────────────────────────
def part_e(A, T):
    """30일 안에 거래량 2배↑ 급락일(-8%↓ 또는 갭 -5%↓) → 그 저가가 5일 이상 지켜짐 → 20일 안 ±3% 갭 2번↑(흔들기)
    → 오늘 5·10일선이 1% 안에 붙고 짧은 캔들(몸통 1.5% 이하)·거래량 20일 평균 70% 이하·종가가 급락일 저가 위 → 다음날 시가 매수"""
    rows = []
    for t, x in T.items():
        n = len(x["c"])
        if n < 80:
            continue
        o, h, l, c, v = x["o"], x["h"], x["l"], x["c"], x["v"]
        pc = np.r_[np.nan, c[:-1]]
        ret = c / pc - 1; gap = o / pc - 1
        va = pd.Series(v).rolling(20).mean().shift(1).values
        crash = ((ret <= -0.08) | (gap <= -0.05)) & (v >= 2 * va)
        ma5 = pd.Series(c).rolling(5).mean().values; ma10 = pd.Series(c).rolling(10).mean().values
        biggap = (np.abs(gap) >= 0.03).astype(float)
        gcnt = pd.Series(biggap).rolling(20).sum().values
        lastk = -99
        for k in range(40, n - 21):
            if k - lastk < 20:
                continue
            if not (abs(ma5[k] / ma10[k] - 1) <= 0.01 and abs(c[k] - o[k]) / c[k] <= 0.015 and v[k] <= 0.7 * va[k] and gcnt[k] >= 2):
                continue
            cs = np.where(crash[max(0, k - 30):k - 5])[0]
            if not len(cs):
                continue
            j = max(0, k - 30) + cs[-1]
            if l[j + 1:k + 1].min() < l[j] or c[k] < l[j]:
                continue
            lastk = k
            e = o[k + 1]; cst = x["cost"][k + 1]
            rows.append((x["d"][k], (c[k + 5] / e - 1) * 100 - cst, (c[k + 10] / e - 1) * 100 - cst, (c[k + 20] / e - 1) * 100 - cst))
    E = pd.DataFrame(rows, columns=["date", "r5", "r10", "r20"])
    P(""); P("## E 앨런 팔리 '사악한 기획' — 급락·멈춤·흔들기 뒤 이평 밀집(부자회사원/리노 ABC)"); P("")
    stats_head()
    for c_ in ("r5", "r10", "r20"):
        stats_row("E %s일 보유" % c_[1:], E[c_].values, E.date.values)


# ── F 와조스키 1차 파동 뒤 눌림 ───────────────────────────────────────────────
def part_f(A, T):
    """1차 파동 = 40일 안에 10일 동안 +30%↑ & 그 구간 거래량이 앞 60일 평균의 2배↑ → 오늘 20일선 ±3% 안으로 눌림
    · 최근 5일 거래량이 파동 구간 평균의 50% 이하 · 120일선 위(하락 추세 아님) · 5일선 아래(정배열 추격 금지)
    → 다음날 시가 매수 · 10일(2주) 보유 · 손절 -10%(종가)"""
    rows = []
    for t, x in T.items():
        n = len(x["c"])
        if n < 200:
            continue
        o, h, l, c, v = x["o"], x["h"], x["l"], x["c"], x["v"]
        cs = pd.Series(c); vs = pd.Series(v)
        ma5 = cs.rolling(5).mean().values; ma20 = cs.rolling(20).mean().values; ma120 = cs.rolling(120).mean().values
        r10 = (cs / cs.shift(10) - 1).values
        v10 = vs.rolling(10).mean().values; v60p = vs.rolling(60).mean().shift(10).values
        wave = (r10 >= 0.30) & (v10 >= 2 * v60p)
        v5 = vs.rolling(5).mean().values
        lastk = -99
        for k in range(130, n - 11):
            if k - lastk < 20:
                continue
            if not (abs(c[k] / ma20[k] - 1) <= 0.03 and c[k] > ma120[k] and c[k] < ma5[k]):
                continue
            w = np.where(wave[k - 40:k - 3])[0]
            if not len(w):
                continue
            j = k - 40 + w[-1]
            if v5[k] > 0.5 * v10[j]:
                continue
            lastk = k
            e = o[k + 1]; cst = x["cost"][k + 1]; res = None
            for d in range(k + 1, k + 11):
                if c[d] <= e * 0.9:
                    res = (c[d] / e - 1) * 100; break
            if res is None:
                res = (c[k + 10] / e - 1) * 100
            rows.append((x["d"][k], res - cst, (c[k + 10] / e - 1) * 100 - cst))
    E = pd.DataFrame(rows, columns=["date", "rs", "r10"])
    P(""); P("## F 1차 파동 뒤 20일선 눌림(와조스키)"); P("")
    stats_head()
    stats_row("F 10일 보유·손절 -10%", E.rs.values, E.date.values)
    stats_row("F 10일 보유(손절 없음)", E.r10.values, E.date.values)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    pick = set(argv) or {"a", "b", "c", "d", "e", "f"}
    t0 = time.time()
    A = load(); T = arrays(A)
    P("# 유튜브 스윙 기법 다섯 편 실측 · %s" % time.strftime("%Y-%m-%d"))
    if "a" in pick: part_a(A, T)
    if "b" in pick: part_b(A, T)
    if "c" in pick: part_c(A, T)
    if "d" in pick: part_d(A, T)
    if "e" in pick: part_e(A, T)
    if "f" in pick: part_f(A, T)
    log_trials("yt_swing_%s" % time.strftime("%Y%m%d"), 12)
    P(""); P("(%.0f분)" % ((time.time() - t0) / 60))
    (ROOT / "reports" / ("yt_swing_%s_%s.md" % (time.strftime("%Y%m%d"), "".join(sorted(pick))))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
