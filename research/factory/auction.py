# -*- coding: utf-8 -*-
"""장전·마감 동시호가 녹화기 (2026-10-08 사용자 아이디어 ③ — 과거 자료가 아무 데도 없는 재료를 오늘부터 쌓는다).

살아남은 데이 규칙(T1·T2)은 전부 '장 전에 고르고 시가 단일가에 산다'. 그런데 장전 30분 동안 예상체결가·잔량이
어떻게 움직였는지는 과거 자료가 없다 → 매일 녹화해 두면 석 달 뒤부터 우리만 가진 재료가 된다.

  아침 08:00~09:00
    NXT 장전(08:00~08:50) 체결가 — 1분마다 전 종목(/prices 200종목 묶음 13번)
    호가 10단계(장전 단일가 08:30~) — 유니버스(거래대금 상위 40%) 약 1,000종목 × 5번
      08:30:30 · 08:36 · 08:42 · 08:47 · 08:56:15(마지막 — 08:59 전에 끝난다)
      ⚠ 데이 아침 선별(day_alert 08:40~08:55)과 토스 한도(초당 20회)를 나눠 쓴다: 이쪽은 초당 7회,
        08:51:30~08:56 사이에 day_alert 가 돌고 있으면(data/m1/.busy) 쉰다.
  마감 15:19~15:31
    15:19:50 전 종목 현재가(= 접속매매 마지막 가격) · 호가 10단계 × 3번(15:20:20 · 15:24:30 · 15:27:20)
저장: data/factory/auction/KR_YYYYMMDD_{am,pm}.parquet(호가) · _nxt.parquet(체결가)
재료(features): 예상가(호가로 맞춘 단일가 균형가격) · 변화 · 잔량 쏠림 · NXT 마지막 체결가 → 저녁 정답지·그림자에 들어간다.
"""
import time, datetime as dt
import numpy as np, pandas as pd

import common as C

AD = C.DATA / "auction"; AD.mkdir(exist_ok=True)
RATE = 7.0
AM = [(8, 30, 30), (8, 36, 0), (8, 42, 0), (8, 47, 0), (8, 56, 15)]
PM = [(15, 20, 20), (15, 24, 30), (15, 27, 20)]


def uni_today():
    """어제까지 일봉(live)으로 오늘 유니버스(거래대금 20일 평균 상위 40%·1,000원↑) — 없으면 전 종목."""
    import live
    try:
        A = live.update()
        last = sorted(A.date.unique())[-21:]
        Z = A[A.date.isin(last)].assign(amt=lambda x: x.close * x.volume)
        g = Z.groupby("ticker")
        px = g.close.last(); a20 = g.amt.mean()
        ok = (px >= 1000) & (g.size() >= 3)
        a20 = a20[ok]
        return sorted(a20[a20.rank(pct=True) >= 0.60].index), px.to_dict()
    except Exception as ex:
        C.log("유니버스 못 만듦 — 전 종목 호가는 건너뜀:", repr(ex)[:200])
        return [], {}


def ob_pass(M, syms, tag):
    rows, t0 = [], time.time()
    from concurrent.futures import ThreadPoolExecutor

    def one(s):
        r = M.get("/api/v1/orderbook", symbol=s) or {}
        out = []
        for side, key in (("A", "asks"), ("B", "bids")):
            for i, x in enumerate(r.get(key) or []):
                try: out.append((tag, s, side, i, float(x["price"]), float(x["volume"])))
                except Exception: pass
        return out
    with ThreadPoolExecutor(3) as ex:
        for r in ex.map(one, syms): rows += r
    C.log("호가 %s %d종목 · %.0f초" % (tag, len(syms), time.time() - t0))
    return rows


def px_pass(M, syms, tag, day):
    rows = []
    for i in range(0, len(syms), 200):
        for x in M.get("/api/v1/prices", symbols=",".join(syms[i:i + 200])) or []:
            ts = x.get("timestamp") or ""
            rows.append((tag, x["symbol"], float(x["lastPrice"]), ts, ts[:10].replace("-", "") == day))
    return rows


def _save(path, rows, cols):
    if not rows: return
    D = pd.DataFrame(rows, columns=cols)
    if path.exists(): D = pd.concat([pd.read_parquet(path), D], ignore_index=True)
    D.to_parquet(path, index=False)


def _day_busy():
    p = C.BASE / "data" / "m1" / ".busy"
    try: return p.exists() and p.read_text().strip() == "day"
    except Exception: return False


def morning(day):
    M = C.toss(RATE)
    U, _ = uni_today()
    ALL = M.universe("KR")
    C.log("장전 녹화 시작 — 전 종목 %d · 호가 유니버스 %d" % (len(ALL), len(U)))
    fo, fx = AD / ("KR_%s_am.parquet" % day), AD / ("KR_%s_nxt.parquet" % day)
    plan = [C.at(*t) for t in AM]
    end = C.at(8, 59, 40)
    with C.Busy("rec"):
        while C.now() < end:
            nxt_ob = plan[0] if plan else None
            if nxt_ob and C.now() >= nxt_ob:
                plan.pop(0)
                need = len(U) / RATE * 1.15
                if nxt_ob.hour == 8 and nxt_ob.minute >= 51:
                    while _day_busy() and C.now() < C.at(8, 56, 30): time.sleep(5)    # 데이 선별이 끝나야
                if (end - C.now()).total_seconds() < need:
                    U2 = U[: int(max((end - C.now()).total_seconds(), 0) / 1.15 * RATE)]
                    C.log("시간 모자라 호가 %d종목만" % len(U2))
                else:
                    U2 = U
                if U2:
                    _save(fo, ob_pass(M, U2, C.now().strftime("%H%M%S")), ["tag", "ticker", "side", "lvl", "price", "vol"])
                continue
            if C.at(8, 0) <= C.now() and not (C.at(8, 51, 30) <= C.now() <= C.at(8, 55, 30) and _day_busy()):
                _save(fx, px_pass(M, ALL, C.now().strftime("%H%M%S"), day), ["tag", "ticker", "price", "ts", "today"])
            nx = min([p for p in plan] + [C.now().replace(second=0, microsecond=0) + dt.timedelta(minutes=1)])
            C.sleep_until(nx)
    C.log("장전 녹화 끝")


def close(day):
    M = C.toss(RATE)
    U, _ = uni_today()
    fo, fx = AD / ("KR_%s_pm.parquet" % day), AD / ("KR_%s_pmpx.parquet" % day)
    with C.Busy("rec"):
        C.sleep_until(C.at(15, 19, 50))
        _save(fx, px_pass(M, U, "151950", day), ["tag", "ticker", "price", "ts", "today"])
        for t in PM:
            C.sleep_until(C.at(*t))
            if U: _save(fo, ob_pass(M, U, C.now().strftime("%H%M%S")), ["tag", "ticker", "side", "lvl", "price", "vol"])
    C.log("마감 녹화 끝")


# ── 재료 ──────────────────────────────────────────────────────────────
def eq_price(P, V, S):
    """호가(가격·잔량·매도A/매수B)로 단일가 균형가격 — 체결량 최대, 같으면 매수·매도 차가 작은 값. 안 겹치면 최우선 호가 가운데."""
    P, V, S = np.asarray(P, float), np.asarray(V, float), np.asarray(S)
    a, b = S == "A", S == "B"
    if not a.any() and not b.any(): return np.nan
    best, bk = np.nan, (-1.0, 0.0)
    for p in np.unique(P):
        d = V[b & (P >= p)].sum(); s = V[a & (P <= p)].sum()
        k = (min(d, s), -abs(d - s))
        if k > bk: best, bk = p, k
    if bk[0] <= 0:
        pa = P[a].min() if a.any() else np.nan; pb = P[b].max() if b.any() else np.nan
        return np.nanmean([pa, pb])
    return best


def _book(f):
    if not f.exists(): return None
    D = pd.read_parquet(f)
    out = []
    for (tag, t), g in D.groupby(["tag", "ticker"], sort=False):
        bv, av = g.vol[g.side == "B"].sum(), g.vol[g.side == "A"].sum()
        out.append((tag, t, eq_price(g.price, g.vol, g.side), (bv - av) / (bv + av) if bv + av > 0 else np.nan))
    return pd.DataFrame(out, columns=["tag", "ticker", "eq", "imb"])


def features(day):
    """그날 녹화로 종목별 재료표(ticker · eq31 첫 호가 균형가 · eq59 마지막 · imb59 · nxt · ceq · cimb · p1520)."""
    cache = AD / ("feat_%s.parquet" % day)
    if cache.exists(): return pd.read_parquet(cache)
    am, pm = _book(AD / ("KR_%s_am.parquet" % day)), _book(AD / ("KR_%s_pm.parquet" % day))
    if am is None and pm is None: return None
    F = pd.DataFrame({"ticker": pd.Series(dtype=str)})
    if am is not None and len(am):
        tags = sorted(am.tag.unique())
        f0, f1 = am[am.tag == tags[0]].set_index("ticker"), am[am.tag == tags[-1]].set_index("ticker")
        F = pd.DataFrame({"eq31": f0["eq"], "eq59": f1["eq"], "imb59": f1["imb"]}).rename_axis("ticker").reset_index()
    fx = AD / ("KR_%s_nxt.parquet" % day)
    if fx.exists():
        X = pd.read_parquet(fx)
        X = X[X.today & (X.tag <= "085000")].sort_values("tag").groupby("ticker").price.last().rename("nxt").reset_index()
        F = F.merge(X, on="ticker", how="outer")
    if pm is not None and len(pm):
        f1 = pm[pm.tag == sorted(pm.tag.unique())[-1]].set_index("ticker")
        F = F.merge(pd.DataFrame({"ceq": f1["eq"], "cimb": f1["imb"]}).rename_axis("ticker").reset_index(), on="ticker", how="outer")
    fp = AD / ("KR_%s_pmpx.parquet" % day)
    if fp.exists():
        X = pd.read_parquet(fp).groupby("ticker").price.last().rename("p1520").reset_index()
        F = F.merge(X, on="ticker", how="outer")
    for k in ("eq31", "eq59", "imb59", "nxt", "ceq", "cimb", "p1520"):
        if k not in F.columns: F[k] = np.nan
    if C.now().strftime("%Y%m%d") > day or C.now().hour >= 16: F.to_parquet(cache, index=False)
    return F
