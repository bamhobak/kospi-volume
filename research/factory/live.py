# -*- coding: utf-8 -*-
"""매일 자료 — 1분봉(09:01~15:31 = KRX 정규장)으로 일봉을 만들어 과거와 **같은 함수(feats.make)**로 재료를 붙인다.

⚠ 토스 일봉은 NXT(넥스트레이드) 장전·장후까지 섞인 통합 봉이라 쓰면 안 된다
   (2026-10-08 삼성전자: 토스 일봉 시가 270,000·종가 263,000 vs KRX 시가 단일가 269,500·종가 단일가 264,500).
   1분봉 첫 봉(09:01) 시가 = 시가 단일가 · 마지막 봉(15:31) 종가 = 종가 단일가.
처음 한 번: 1분봉 과거 채우기(bf, 상위 1,000종목 ~10-01) + 매일 파일(day, 10-02~)로 최근 200거래일 일봉을 만든다(seed).
그 뒤 매일 저녁: 오늘 매일 파일만 일봉으로 바꿔 덧붙인다(update).
"""
import glob, time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd

import common as C
import feats as FT

LD = C.DATA / "live"; LD.mkdir(exist_ok=True)
DAILY = LD / "kr_daily.parquet"
M1 = C.BASE / "data" / "m1" / "KR"


def agg(D, since=None):
    """1분봉(t ts o h l c v) → 일봉. 시가는 첫 봉이 09:01 일 때만(그래야 시가 단일가)."""
    k = D.ts.to_numpy().astype("int64") + 9 * 3600                     # 한국 시각(초) — 글자 변환은 날짜별 한 번만(빠르게)
    dn, sec = k // 86400, k % 86400
    ud = np.unique(dn)
    dstr = dict(zip(ud, pd.to_datetime(ud, unit="D").strftime("%Y%m%d")))
    hm = (sec // 3600) * 100 + (sec % 3600) // 60
    D = D.assign(date=pd.Series(dn, index=D.index).map(dstr).values, hm=np.char.zfill(hm.astype(str), 4))
    if since: D = D[D.date >= since]
    D = D[(D.hm >= "0901") & (D.hm <= "1531")].sort_values(["t", "ts"])
    if D.empty: return pd.DataFrame(columns=["ticker", "date", "open", "high", "low", "close", "volume"])
    g = D.groupby(["t", "date"], sort=False)
    R = pd.DataFrame({"open": g.o.first(), "high": g.h.max(), "low": g.l.min(), "close": g.c.last(), "volume": g.v.sum(),
                      "first": g.hm.first(), "n": g.size()}).reset_index().rename(columns={"t": "ticker"})
    R.loc[R["first"] != "0901", "open"] = np.nan
    R = R[R.n >= 5].drop(columns=["first", "n"])
    for k in ("open", "high", "low", "close"): R[k] = R[k].astype("float64")
    R["volume"] = R.volume.astype("float64")
    return R


def _one_bf(args):
    f, since = args
    try: return agg(pd.read_parquet(f), since)
    except Exception: return None


def seed(days=200):
    t0 = time.time()
    dayfiles = sorted(glob.glob(str(M1 / "day" / "*.parquet")))
    since = (pd.Timestamp.now() - pd.Timedelta(days=int(days * 1.5))).strftime("%Y%m%d")
    out = []
    with ProcessPoolExecutor(8) as ex:
        for r in ex.map(_one_bf, [(f, since) for f in glob.glob(str(M1 / "bf" / "*.parquet"))], chunksize=8):
            if r is not None and len(r): out.append(r)
    for f in dayfiles:
        out.append(agg(pd.read_parquet(f)))
    A = pd.concat(out, ignore_index=True).drop_duplicates(["ticker", "date"], keep="last").sort_values(["ticker", "date"])
    A.to_parquet(DAILY, index=False)
    C.log("매일 자료 처음 만들기: %d종목 · %d일 · %.1f분" % (A.ticker.nunique(), A.date.nunique(), (time.time() - t0) / 60))
    return A


def update():
    """매일 파일 중 아직 안 넣은 날을 넣는다(PC 꺼져 빠진 날도)."""
    if not DAILY.exists(): return seed()
    A = pd.read_parquet(DAILY)
    have = set(A.date.unique())
    new = [f for f in sorted(glob.glob(str(M1 / "day" / "*.parquet"))) if Path(f).stem not in have]
    if new:
        A = pd.concat([A] + [agg(pd.read_parquet(f)) for f in new], ignore_index=True)
        keep = sorted(A.date.unique())[-260:]
        A = A[A.date.isin(keep)].drop_duplicates(["ticker", "date"], keep="last").sort_values(["ticker", "date"])
        A.to_parquet(DAILY, index=False)
        C.log("매일 자료 덧붙임:", ", ".join(Path(f).stem for f in new))
    return A


def fill_missing(days=62, rate=8.0):
    """최근 거래일에 있는데 일봉 기록이 days 일보다 짧은 종목(1분봉 과거 채우기 상위 1,000 밖)을 1분봉으로 메운다.
    안 메우면 그 종목들(유니버스의 약 1/4)은 20·60일 재료가 몇 주 동안 빈칸이다(2026-10-08 점검기가 잡음)."""
    from concurrent.futures import ThreadPoolExecutor
    M = C.toss(rate)
    A = pd.read_parquet(DAILY)
    cal = sorted(A[A.ticker == "005930"].date.unique())[-days:]
    have = A[A.date.isin(cal)].groupby("ticker").date.apply(set)
    last = cal[-1]
    R = A[A.date.isin(cal[-5:])].assign(amt=lambda x: x.close * x.volume).groupby("ticker").amt.mean()
    tick = sorted(R[R.rank(pct=True) >= 0.45].index.intersection(A[A.date == last].ticker.unique()))   # 유니버스(상위 40%)에 들 만한 종목만
    todo = [(t, d) for t in tick for d in cal if d not in have.get(t, set())]
    C.log("빈 일봉 메우기: %d종목 · %d종목-일" % (len({t for t, _ in todo}), len(todo)))
    rows, t0 = [], time.time()
    with C.Busy("fac"), ThreadPoolExecutor(3) as ex:
        for i, r in enumerate(ex.map(lambda td: M.fetch_day("KR", td[0], td[1]), todo)):
            rows += r
            if i % 2000 == 1999: C.log("  %d/%d · %.0f분" % (i + 1, len(todo), (time.time() - t0) / 60))
    if rows:
        N = agg(M.frame(rows))
        A = pd.concat([A, N], ignore_index=True).drop_duplicates(["ticker", "date"], keep="first").sort_values(["ticker", "date"])
        A.to_parquet(DAILY, index=False)
    C.log("빈 일봉 메우기 끝: %d줄 · %.0f분" % (len(rows), (time.time() - t0) / 60))


def snap_m1(day):
    """그날 1분봉 단면 — 10:00·14:00·15:19 까지 가격·VWAP·고저·거래량 + 시가·종가(장중 방식·종가 매수 15:19 재검용)."""
    f = M1 / "day" / ("%s.parquet" % day)
    if not f.exists(): return None
    D = pd.read_parquet(f)
    k = D.ts.to_numpy().astype("int64") + 9 * 3600
    hm = ((k % 86400) // 3600) * 100 + (k % 3600) // 60
    D = D.assign(hm=hm)[(hm >= 901) & (hm <= 1531)].sort_values(["t", "ts"])
    D["pv"] = D.c.astype(float) * D.v.astype(float)
    g = D.groupby("t")
    out = {"o_m": g.o.first(), "c_m": g.c.last(), "vol_m": g.v.sum()}
    for t in ("1000", "1400", "1519"):
        E = D[D.hm <= int(t)]; ge = E.groupby("t")
        out.update({"p" + t: ge.c.last(), "hi" + t: ge.h.max(), "lo" + t: ge.l.min(), "v" + t: ge.v.sum(),
                    "vw" + t: ge.pv.sum() / ge.v.sum().replace(0, np.nan)})
    R = pd.DataFrame(out).astype(float).rename_axis("ticker").reset_index()
    R.loc[g.hm.first().reindex(R.ticker).to_numpy() != 901, "o_m"] = np.nan          # 첫 봉이 09:01 이 아니면 시가 단일가가 아님
    return R.assign(date=day)


def snap1519(day):
    R = snap_m1(day)
    return None if R is None else R[["ticker", "p1519", "hi1519", "lo1519", "v1519", "vol_m"]]


def names(force=False):
    p = C.DATA / "names.json"
    j = C.jload(p, {})
    if j and not force and time.time() - p.stat().st_mtime < 7 * 86400: return j
    M = C.toss(rate=8)
    U = M.universe("KR")
    meta = {}
    for i in range(0, len(U), 100):
        for x in M.get("/api/v1/stocks", symbols=",".join(U[i:i + 100])) or []:
            j[x["symbol"]] = x.get("name") or x["symbol"]
            meta[x["symbol"]] = {"shares": float(x.get("sharesOutstanding") or 0) or None, "list": (x.get("listDate") or "").replace("-", "")}
    C.jsave(p, j); C.jsave(C.DATA / "meta.json", meta)            # 시가총액(발행 주식 수)·상장 후 일수(상장일) 재료용
    return j


def meta():
    m = C.jload(C.DATA / "meta.json", {})
    if not m: names(force=True); m = C.jload(C.DATA / "meta.json", {})
    return m


def frame(days=None, A=None):
    """최근 일봉으로 재료를 만든다 → 유니버스 줄만(q_ 포함). days = 돌려받을 날짜 목록(없으면 마지막 날)."""
    import lab
    A = update() if A is None else A
    keep = sorted(A.date.unique())[-260:]                               # 52주·224일선 재료가 250일을 본다
    A = A[A.date.isin(keep)]
    mt = meta()
    A = A.assign(shares=A.ticker.map(lambda t: (mt.get(t) or {}).get("shares")))
    fl = lab.load_flows(since=keep[0])
    X = FT.make(A, fl, lab.load_themes(), seam=False, amt_mp=3)
    days = days or [keep[-1]]
    U = X[X.uni & X.date.isin(days)].drop(columns=["uni"]).reset_index(drop=True)
    # 상장 후 일수 — 매일 자료는 260일뿐이라 상장일로(과거 자료와 같게 250 에서 자른다)
    lst = U.ticker.map(lambda t: (mt.get(t) or {}).get("list") or "")
    dd = (pd.to_datetime(U.date) - pd.to_datetime(lst, errors="coerce")).dt.days * 250 / 365
    U["age"] = np.where(dd.notna(), np.minimum(dd, 250), U.age)
    attach_transfer(U)
    attach_auction(U)
    Ms = [m for m in (snap_m1(d) for d in sorted(U.date.unique())) if m is not None]     # 장중 재료·목표(m10c·m14c)
    if Ms:
        M = pd.concat(Ms, ignore_index=True).merge(U[["ticker", "date", "amt20"]], on=["ticker", "date"], how="left")
        FT.intra(U, M.assign(amt20_m=M.amt20 * 1e8).drop(columns=["amt20"]))
    else:
        for k in list(FT.INTRA) + ["m10c", "m14c"]: U[k] = np.nan
    return FT.shrink(FT.qcols(U, [f for f in FT.FEATS if f in U.columns]))


def attach_transfer(U):
    for k in ("us_ewy", "tr_us", "tr_pred", "tr_res"): U[k] = np.nan
    for d in U.date.unique():
        j = C.jload(C.DATA / "transfer" / ("%s.json" % d))
        if not j: continue
        m = (U.date == d).to_numpy()
        U.loc[m, "us_ewy"] = j["inst"].get("EWY", np.nan)
        P = j["pred"]
        tk = U.loc[m, "ticker"]
        U.loc[m, "tr_us"] = tk.map(lambda t: (P.get(t) or [None, None, None])[2]).astype(float).values
        U.loc[m, "tr_pred"] = tk.map(lambda t: (P.get(t) or [None, None, None, None])[3]).astype(float).values
        U.loc[m, "tr_res"] = U.loc[m, "gap"] - U.loc[m, "tr_pred"]


def attach_auction(U):
    import auction as AU
    for k in ("a_eq", "a_drift", "a_imb", "a_nxt", "a_err", "c_imb", "c_drift"): U[k] = np.nan
    for d in U.date.unique():
        F = AU.features(d)
        if F is None or F.empty: continue
        m = (U.date == d).to_numpy()
        S = U.loc[m, ["ticker", "px", "gap", "oct"]].merge(F, on="ticker", how="left")
        pc = S.px.astype(float)
        U.loc[m, "a_eq"] = ((S.eq59 / pc - 1) * 100).values
        U.loc[m, "a_drift"] = ((S.eq59 - S.eq31) / pc * 100).values
        U.loc[m, "a_imb"] = S.imb59.values
        U.loc[m, "a_nxt"] = ((S.nxt / pc - 1) * 100).values
        U.loc[m, "a_err"] = (U.loc[m, "a_eq"].values - S.gap.values)
        U.loc[m, "c_imb"] = S.cimb.values
        U.loc[m, "c_drift"] = ((S.ceq / S.p1520 - 1) * 100).values
