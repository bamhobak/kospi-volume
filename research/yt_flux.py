# -*- coding: utf-8 -*-
"""유튜브 'The 3 BEST AI Indicators on TradingView'(Flux Charts · 7BTHM000us4) 실측 (2026-10-11, 사용자 링크).

영상 주장 → 일봉 규칙으로 옮김 (전부 '그날 종가까지 아는 것'만 쓰고, 기계학습은 해마다 과거 거래만으로 다시 학습)
  A AI 슈퍼트렌드(KNN): 슈퍼트렌드(ATR10·배수3) 상승 전환 → 다음날 시가 매수.
      청산 ① 하락 전환(종가) 다음날 시가 ② 장중 슈퍼트렌드 선 손절. 영상 = '확신 70%↑ 만' → 과거 전환 거래로 KNN(이웃 50)
      학습해 이번 전환의 승률 추정, 70%↑·60%↑·전년 상위 20% 문턱 판. 영상 주장 승률 ~60% · 1.5R.
  B 지지/저항 로지스틱 회귀: 피벗 저점(좌우 5봉) 수평선을 위에서 내려와 다시 터치하고 위에서 마감(재시험) → 다음날 시가 매수,
      손절 = 선 아래 ATR 0.5, 목표 2R, 40일 안 끝. 영상 = '지켜질 확률 70%↑ 선만' → 로지스틱 회귀로 목표 도달 확률 추정.
      영상 주장 승률 70% · 2R. (저항 공매도 쪽은 우리가 안 하므로 뺌)
  C 신경망 일 단위 상태(매수/관망/현금): 유니버스 같은 비중 지수에 작은 신경망(MLP)으로 20일 뒤 상승 확률 → 0.55↑ 만 보유.
      영상 주장 = 큰 상승장의 70% 를 탄다.
  SFX Algo 는 유료 광고라 뺌.
  우리 재료 조합(국장): [갭 하락 조용주] T1 을 슈퍼트렌드 방향 · 시장 상태 · '시가가 지지선에 닿음/뚫음' 으로 갈라 본다.

    python research/yt_flux.py KR
    python research/yt_flux.py US
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
from numba import njit

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
import run_spec as R
from verdict import log_trials

OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
PER = [("옛날 ~15", "00000000", "20151231"), ("학습 16~22", "20160101", "20221231"), ("검증 23~", "20230101", "20991231")]


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


# ── 계산 (numba) ───────────────────────────────────────────────────────────────
@njit(cache=True)
def st_calc(tk, h, l, c, atr, mult):
    n = len(c); tr = np.full(n, -1.0); line = np.full(n, np.nan)
    fu = np.nan; fl = np.nan; up = True
    for i in range(n):
        if i == 0 or tk[i] != tk[i - 1]:
            fu = np.nan; fl = np.nan; up = True
        a = atr[i]
        if not (a == a):
            continue
        mid = (h[i] + l[i]) / 2; ub = mid + mult * a; lb = mid - mult * a
        pc_ = c[i - 1] if (i > 0 and tk[i] == tk[i - 1]) else c[i]
        if not (fu == fu) or ub < fu or pc_ > fu:
            fu = ub
        if not (fl == fl) or lb > fl or pc_ < fl:
            fl = lb
        if up and c[i] < fl:
            up = False
        elif (not up) and c[i] > fu:
            up = True
        tr[i] = 1.0 if up else 0.0
        line[i] = fl if up else fu
    return tr, line


@njit(cache=True)
def st_trades(tk, o, h, l, c, tr, line, mode, maxhold):
    """상승 전환일 d → d+1 시가 매수. mode 0 = 하락 전환(종가) 다음날 시가 · mode 1 = 장중 전날 선 손절."""
    n = len(c)
    S = np.empty(n, np.int64); X = np.empty(n, np.int64); RT = np.empty(n); RK = np.empty(n); RM = np.empty(n); k = 0
    for d in range(1, n - 1):
        if tk[d] != tk[d - 1] or tk[d + 1] != tk[d]:
            continue
        if not (tr[d] == 1.0 and tr[d - 1] == 0.0):
            continue
        e = o[d + 1]
        if not (e > 0) or not (line[d] < e):
            continue
        risk = e - line[d]
        j = d + 1; px = np.nan; xi = -1
        while j < n and tk[j] == tk[d]:
            if j - d > maxhold:
                px = c[j - 1]; xi = j - 1; break
            if mode == 1:
                stp = line[j - 1]
                if j > d + 1 and o[j] <= stp:
                    px = o[j]; xi = j; break
                if l[j] <= stp:
                    px = stp; xi = j; break
            if tr[j] == 0.0:
                if j + 1 < n and tk[j + 1] == tk[d]:
                    px = o[j + 1]; xi = j + 1
                break
            j += 1
        if xi < 0 or not (px > 0):
            continue
        S[k] = d; X[k] = xi; RT[k] = (px / e - 1) * 100; RK[k] = risk / e * 100; RM[k] = (px - e) / risk; k += 1
    return S[:k], X[:k], RT[:k], RK[:k], RM[:k]


@njit(cache=True)
def sr_scan(tk, o, h, l, c, atr, pv, maxhold):
    """피벗 저점 수평선 재시험 거래 + 날마다 '시가가 지지선에 닿음/뚫음' 표시."""
    n = len(c); ML = 12
    lvP = np.zeros(ML); lvI = np.zeros(ML, np.int64); lvT = np.zeros(ML, np.int64); nl = 0
    sup_on = np.zeros(n, np.int8); sup_brk = np.zeros(n, np.int8)
    E_t = np.empty(n, np.int64); E_x = np.empty(n, np.int64); E_ret = np.empty(n); E_win = np.empty(n); E_rm = np.empty(n)
    E_touch = np.empty(n); E_age = np.empty(n); E_depth = np.empty(n); E_risk = np.empty(n); k = 0
    start = 0; busy = -1
    for t in range(n):
        if t == 0 or tk[t] != tk[t - 1]:
            start = t; nl = 0; busy = -1
        if t > start and atr[t - 1] == atr[t - 1]:
            a1 = atr[t - 1]
            for q in range(nl):
                L = lvP[q]
                if c[t - 1] > L + 0.25 * a1:
                    if o[t] >= L - 0.5 * a1 and o[t] <= L + 0.25 * a1:
                        sup_on[t] = 1
                    elif o[t] < L - 0.5 * a1:
                        sup_brk[t] = 1
        i = t - pv
        if i - pv >= start:
            ok = True
            for q in range(i - pv, t + 1):
                if l[q] < l[i]:
                    ok = False; break
            if ok and l[i] > 0:
                if nl == ML:
                    for q in range(ML - 1):
                        lvP[q] = lvP[q + 1]; lvI[q] = lvI[q + 1]; lvT[q] = lvT[q + 1]
                    nl -= 1
                lvP[nl] = l[i]; lvI[nl] = i; lvT[nl] = 0; nl += 1
        a = atr[t]
        if not (a == a) or t == start:
            continue
        q = 0
        while q < nl:
            if c[t] < lvP[q] - 0.5 * a:
                for r in range(q, nl - 1):
                    lvP[r] = lvP[r + 1]; lvI[r] = lvI[r + 1]; lvT[r] = lvT[r + 1]
                nl -= 1
            else:
                q += 1
        best = -1
        for q in range(nl):
            L = lvP[q]
            if t - lvI[q] < 10 + pv:
                continue
            if l[t] <= L + 0.25 * a and c[t] > L and c[t - 1] > L + 0.5 * a:
                if best < 0 or L > lvP[best]:
                    best = q
        if best < 0:
            continue
        L = lvP[best]
        touches = lvT[best]; lvT[best] += 1
        if t <= busy or t + 1 >= n or tk[t + 1] != tk[t]:
            continue
        e = o[t + 1]; stop = L - 0.5 * a
        if not (e > stop) or not (e > 0):
            continue
        Rr = e - stop; tgt = e + 2 * Rr
        hh = 0.0
        for q in range(lvI[best], t):
            if h[q] > hh:
                hh = h[q]
        px = np.nan; win = 0.0; xi = -1
        j = t + 1
        while j < n and tk[j] == tk[t]:
            if j > t + 1:
                if o[j] <= stop:
                    px = o[j]; xi = j; break
                if o[j] >= tgt:
                    px = o[j]; win = 1.0; xi = j; break
            if l[j] <= stop:
                px = stop; xi = j; break
            if h[j] >= tgt:
                px = tgt; win = 1.0; xi = j; break
            if j - t >= maxhold:
                px = c[j]; xi = j; break
            j += 1
        if xi < 0:
            continue
        busy = xi
        E_t[k] = t; E_x[k] = xi; E_ret[k] = (px / e - 1) * 100; E_win[k] = win; E_rm[k] = (px - e) / Rr
        E_touch[k] = touches; E_age[k] = t - lvI[best]; E_depth[k] = hh / L - 1; E_risk[k] = Rr / e * 100; k += 1
    return (E_t[:k], E_x[:k], E_ret[:k], E_win[:k], E_rm[:k], E_touch[:k], E_age[:k], E_depth[:k], E_risk[:k], sup_on, sup_brk)


# ── 패널 ──────────────────────────────────────────────────────────────────────
def load(mk):
    A, uni, since = R.load_market(mk)
    A["uni"] = uni.values
    A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
    g = A.groupby("ticker", sort=False)
    pc = g.close.shift(1)
    trr = pd.concat([A.high - A.low, (A.high - pc).abs(), (A.low - pc).abs()], axis=1).max(axis=1)
    rma = lambda x, n: x.groupby(A.ticker, sort=False).transform(lambda s: s.ewm(alpha=1 / n, adjust=False, min_periods=n).mean())
    A["atr10"] = rma(trr, 10); A["atr14"] = rma(trr, 14)
    up, dn = (A.close - pc).clip(lower=0), (pc - A.close).clip(lower=0)
    A["rsi14"] = 100 * rma(up, 14) / (rma(up, 14) + rma(dn, 14) + 1e-12)
    for k in (5, 20, 60):
        A["f_r%d" % k] = (A.close / g.close.shift(k) - 1) * 100
    A["f_atrp"] = A.atr14 / A.close * 100
    A["f_vm"] = A.volume / g.volume.transform(lambda s: s.rolling(60, min_periods=20).mean()).replace(0, np.nan)
    A["f_hi60"] = (A.close / g.high.transform(lambda s: s.rolling(60, min_periods=20).max()) - 1) * 100
    A["f_clv"] = (A.close - A.low) / (A.high - A.low).replace(0, np.nan)
    A["f_mkt20"] = A.f_r20.where(A.uni).groupby(A.date).transform("median")
    A["tk"] = pd.factorize(A.ticker)[0].astype(np.int64)
    return A


COMMON = ["f_r5", "f_r20", "f_r60", "f_atrp", "f_vm", "f_hi60", "f_clv", "f_mkt20", "rsi14"]


def walk(E, feats, ylab, make, y0):
    """해마다 그해 1/1 전에 끝난 거래만으로 학습 → 그해 신호 예측. thr = 전년 예측의 상위 20% 문턱(미래 없음)."""
    E = E.copy(); E["p"] = np.nan; E["thr"] = np.nan
    ok = E[feats].notna().all(axis=1) & np.isfinite(E[feats]).all(axis=1)
    prev = None
    for Y in range(y0, int(E.yr.max()) + 1):
        tr = E[ok & (E.xdate < "%d0101" % Y)]
        te = E.index[ok & (E.yr == Y)]
        if len(tr) < 500 or len(te) == 0:
            continue
        m = make(); m.fit(tr[feats].clip(tr[feats].quantile(.01), tr[feats].quantile(.99), axis=1).values, tr[ylab].values)
        X = E.loc[te, feats].clip(tr[feats].quantile(.01), tr[feats].quantile(.99), axis=1).values
        E.loc[te, "p"] = m.predict_proba(X)[:, 1]
        if prev is not None:
            E.loc[te, "thr"] = prev
        prev = float(np.quantile(E.loc[te, "p"], .8))
    return E


def per_of(d):
    return 0 if d <= "20151231" else (1 if d <= "20221231" else 2)


def head(extra="평균R"):
    P("| 판 | 옛날 ~15 건수·평균·승률 | 학습 16~22 | 검증 23~ | 검증 %s · 보유일 | 평균 양수 해 |" % extra)
    P("|---|---|---|---|---|---|")


def row(lab, E, m, rcol="ret", rm="rm"):
    S = E[m]
    cells = [lab]
    for i, (_, a, b) in enumerate(PER):
        w = S[(S.date >= a) & (S.date <= b)]
        cells.append("%s건 %+.2f%% · %.0f%%" % (f"{len(w):,}", w[rcol].mean(), (w[rcol] > 0).mean() * 100) if len(w) >= 20 else "n=%d" % len(w))
    v = S[S.date >= "20230101"]
    cells.append("%+.2fR · %.0f일" % (v[rm].mean(), v.hold.mean()) if len(v) >= 20 else "-")
    ys = S.groupby(S.date.str[:4])[rcol].mean()
    cells.append("%d/%d" % ((ys > 0).sum(), len(ys)))
    P("| " + " | ".join(cells) + " |")


# ── A 슈퍼트렌드 ──────────────────────────────────────────────────────────────
def part_a(A, mk):
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.neighbors import KNeighborsClassifier
    tk = A.tk.values; o, h, l, c = (A[x].values.astype(float) for x in ("open", "high", "low", "close"))
    tr, line = st_calc(tk, h, l, c, A.atr10.values.astype(float), 3.0)
    A["st_tr"] = tr
    dates = A.date.values; cost = A.cost.values.astype(float); uni = A.uni.values
    P(""); P("## A AI 슈퍼트렌드(KNN) — 상승 전환 다음날 시가 매수 · 비용 차감"); P("")
    res = {}
    for mode, ml in ((0, "하락 전환에 청산"), (1, "장중 선 손절")):
        S, X, RT, RK, RM = st_trades(tk, o, h, l, c, tr, line, mode, 500)
        E = pd.DataFrame({"i": S, "date": dates[S], "xdate": dates[X], "ret": RT - cost[S], "rm": RM, "f_risk": RK, "hold": X - S})
        E = E[uni[S]].reset_index(drop=True)
        for f in COMMON:
            E[f] = A[f].values[E.i.values]
        E["yr"] = E.date.str[:4].astype(int); E["win"] = (E.ret > 0).astype(int)
        log("A %s 거래 %d — KNN 학습" % (ml, len(E)))
        E = walk(E, COMMON + ["f_risk"], "win",
                 lambda: make_pipeline(StandardScaler(), KNeighborsClassifier(n_neighbors=50, n_jobs=-1)), 2010)
        res[mode] = E
        head()
        row("%s · 전부" % ml, E, E.ret.notna())
        row("%s · KNN 확신 60%%↑" % ml, E, E.p >= 0.6)
        row("%s · KNN 확신 70%%↑ (영상)" % ml, E, E.p >= 0.7)
        row("%s · KNN 전년 상위 20%% 문턱↑" % ml, E, E.p >= E.thr)
        row("%s · KNN 전년 하위(반대) 40%% 문턱↓" % ml, E, (E.p < E.thr) & E.p.notna())
        P("")
    P("평균R = (청산가 − 진입가) ÷ (진입가 − 슈퍼트렌드 선). 학습 신호 2010~ 부터 예측(그 전은 학습 재료만).")
    return res


# ── B 지지선 재시험 ───────────────────────────────────────────────────────────
def part_b(A, mk):
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    tk = A.tk.values; o, h, l, c = (A[x].values.astype(float) for x in ("open", "high", "low", "close"))
    (Et, Ex, Eret, Ewin, Erm, Etouch, Eage, Edepth, Erisk, sup_on, sup_brk) = sr_scan(tk, o, h, l, c, A.atr14.values.astype(float), 5, 40)
    A["sup_on"] = sup_on; A["sup_brk"] = sup_brk
    dates = A.date.values; cost = A.cost.values.astype(float); uni = A.uni.values
    E = pd.DataFrame({"i": Et, "date": dates[Et], "xdate": dates[Ex], "ret": Eret - cost[Et], "win": Ewin.astype(int), "rm": Erm,
                      "f_touch": Etouch, "f_age": Eage, "f_depth": Edepth * 100, "f_risk": Erisk, "hold": Ex - Et})
    E = E[uni[Et]].reset_index(drop=True)
    for f in COMMON:
        E[f] = A[f].values[E.i.values]
    E["yr"] = E.date.str[:4].astype(int)
    log("B 재시험 거래 %d — 로지스틱 학습" % len(E))
    feats = COMMON + ["f_touch", "f_age", "f_depth", "f_risk"]
    E = walk(E, feats, "win", lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=500, C=1.0)), 2010)
    P(""); P("## B 지지선 재시험(로지스틱 회귀) — 다음날 시가 매수 · 손절 선-ATR0.5 · 목표 2R · 40일 · 비용 차감"); P("")
    head()
    row("재시험 전부", E, E.ret.notna())
    row("지켜질 확률 50%%↑", E, E.p >= 0.5)
    row("지켜질 확률 70%%↑ (영상)", E, E.p >= 0.7)
    row("전년 상위 20%% 문턱↑", E, E.p >= E.thr)
    row("전년 상위 20%% 문턱 아래(나머지)", E, (E.p < E.thr) & E.p.notna())
    row("첫 재시험만(터치 0)", E, E.f_touch == 0)
    row("세 번째 이상 터치", E, E.f_touch >= 2)
    v = E[E.date >= "20230101"]
    P(""); P("목표 2R 도달률(승 = 목표): 전부 %.0f%% · 검증 %.0f%% · 확률 상위 20%% 검증 %.0f%% — 영상 주장 70%%" % (
        E.win.mean() * 100, v.win.mean() * 100, v.loc[v.p >= v.thr, "win"].mean() * 100))
    try:
        m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=500)).fit(E[feats].dropna().values, E.dropna(subset=feats).win.values)
        co = m[-1].coef_[0]
        P("로지스틱 계수(표준화, 전체 기간): " + " · ".join("%s %+.2f" % (f.replace("f_", ""), x) for f, x in sorted(zip(feats, co), key=lambda z: -abs(z[1]))))
    except Exception as ex:
        P("(계수 못 냄 %r)" % ex)
    return E


# ── C 시장 상태 신경망 ────────────────────────────────────────────────────────
def part_c(A, mk):
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.neural_network import MLPClassifier
    pc = A.groupby("ticker", sort=False).close.shift(1)
    r = (A.close / pc - 1).clip(-0.3, 0.3).where(A.uni)
    D = pd.DataFrame({"r": r.groupby(A.date).mean(), "br": (A.f_r60 > 0).where(A.uni).groupby(A.date).mean()}).dropna()
    D["lv"] = (1 + D.r).cumprod()
    for k in (5, 20, 60, 120):
        D["x%d" % k] = D.lv / D.lv.shift(k) - 1
    D["vol"] = D.r.rolling(20).std() * np.sqrt(252)
    D["dd"] = D.lv / D.lv.rolling(250, min_periods=60).max() - 1
    D["f20"] = D.lv.shift(-20) / D.lv - 1; D["f60"] = D.lv.shift(-60) / D.lv - 1
    D["y"] = (D.f20 > 0).astype(int)
    D["yr"] = D.index.str[:4].astype(int); D["di"] = np.arange(len(D))
    feats = ["x5", "x20", "x60", "x120", "vol", "dd", "br"]
    D["p"] = np.nan
    for Y in range(2010, int(D.yr.max()) + 1):
        y0 = D.index[D.yr == Y]
        if len(y0) == 0:
            continue
        first = D.loc[y0[0], "di"]
        tr = D[(D.di < first - 20)].dropna(subset=feats + ["f20"])
        ps = []
        for seed in range(5):
            m = make_pipeline(StandardScaler(), MLPClassifier((16, 8), max_iter=800, random_state=seed, alpha=1e-3))
            m.fit(tr[feats].values, tr.y.values)
            ps.append(m.predict_proba(D.loc[y0, feats].fillna(0).values)[:, 1])
        D.loc[y0, "p"] = np.mean(ps, axis=0)
    D = D[D.p.notna()]
    D["long"] = (D.p >= 0.55).shift(1).fillna(False).astype(bool)      # 어제 종가에 정한 상태로 오늘 보유
    sw = D.long.astype(int).diff().abs().fillna(0)
    D["sr"] = D.r * D.long - sw * 0.001                                 # 바꿀 때마다 0.1%(지수 ETF 왕복 0.2 의 절반씩)
    P(""); P("## C 신경망 일 단위 상태(매수/현금) — 유니버스 같은 비중 지수 · 0.55↑ 만 보유"); P("")
    P("| 기간 | 지수 그냥 보유 연수익·최대낙폭 | 상태 따라 연수익·최대낙폭 | 보유 비율 | 큰 상승(60일 +10%↑) 탄 비율 | 전환 횟수 |"); P("|---|---|---|---|---|---|")

    def cagr_mdd(x):
        lv = (1 + x).cumprod(); yrs = len(x) / 252
        return (lv.iloc[-1] ** (1 / yrs) - 1) * 100, (lv / lv.cummax() - 1).min() * 100
    for lab, a, b in (("2010~15", "2010", "20151231"), ("학습 16~22", "20160101", "20221231"), ("검증 23~", "20230101", "2099")):
        w = D[(D.index >= a) & (D.index <= b)]
        if len(w) < 60:
            continue
        c1, m1 = cagr_mdd(w.r); c2, m2 = cagr_mdd(w.sr)
        big = w.f60 > 0.10
        P("| %s | %+.1f%% · %.0f%% | %+.1f%% · %.0f%% | %.0f%% | %.0f%% | %d |" % (lab, c1, m1, c2, m2, w.long.mean() * 100,
                                                                         w.loc[big, "long"].mean() * 100 if big.any() else np.nan, int(sw.loc[w.index].sum())))
    return D


# ── 우리 재료 조합 (국장 T1) ──────────────────────────────────────────────────
def part_combo(A, D):
    sys.path.insert(0, str(ROOT / "factory"))
    import lab, feats as FT
    U = lab.hist()
    U = U[U.t1 & U.oc.notna()].copy()
    U["ret"] = U.oc.astype(float).clip(-60, 60) - FT.COST
    K = A[["ticker", "date", "sup_on", "sup_brk"]]
    K = K.assign(st_prev=A.groupby("ticker", sort=False).st_tr.shift(1).values)
    U = U.merge(K, on=["ticker", "date"], how="left")
    U["mlong"] = U.date.map(D.long) if D is not None else np.nan
    U["rm"] = 0.0; U["hold"] = 0
    P(""); P("## 우리 재료 조합 — [갭 하락 조용주] T1 을 영상 지표로 갈라 보기 (시가→종가 · 비용 0.23%)"); P("")
    head("-")
    row("T1 전부", U, U.ret.notna())
    row("어제 슈퍼트렌드 상승", U, U.st_prev == 1)
    row("어제 슈퍼트렌드 하락", U, U.st_prev == 0)
    row("시가가 지지선에 닿음(선 -ATR0.5~+0.25)", U, U.sup_on == 1)
    row("시가가 지지선을 뚫음(선 -ATR0.5 아래)", U, U.sup_brk == 1)
    row("지지선 없음/멀리", U, (U.sup_on != 1) & (U.sup_brk != 1))
    if D is not None:
        row("시장 상태 = 매수(신경망 0.55↑)", U, U.mlong == True)
        row("시장 상태 = 현금", U, U.mlong == False)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    mk = (argv[:1] or ["KR"])[0].upper()
    t0 = time.time()
    A = load(mk); log("패널 %s행" % f"{len(A):,}")
    P("# 유튜브 Flux Charts 'AI 지표 3종'(7BTHM000us4) 실측 · %s · %s" % (mk, time.strftime("%Y-%m-%d")))
    part_a(A, mk)
    part_b(A, mk)
    D = part_c(A, mk)
    if mk == "KR":
        part_combo(A, D)
    log_trials("yt_flux_%s_%s" % (mk, time.strftime("%Y%m%d")), 20)
    P(""); P("(%.0f분)" % ((time.time() - t0) / 60))
    (ROOT / "reports" / ("yt_flux_%s_%s.md" % (mk, time.strftime("%Y%m%d")))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
