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


def names(force=False):
    p = C.DATA / "names.json"
    j = C.jload(p, {})
    if j and not force and time.time() - p.stat().st_mtime < 7 * 86400: return j
    M = C.toss(rate=8)
    U = M.universe("KR")
    for i in range(0, len(U), 100):
        for x in M.get("/api/v1/stocks", symbols=",".join(U[i:i + 100])) or []:
            j[x["symbol"]] = x.get("name") or x["symbol"]
    C.jsave(p, j)
    return j


def frame(days=None, A=None):
    """최근 일봉으로 재료를 만든다 → 유니버스 줄만(q_ 포함). days = 돌려받을 날짜 목록(없으면 마지막 날)."""
    import lab
    A = update() if A is None else A
    keep = sorted(A.date.unique())[-150:]
    A = A[A.date.isin(keep)]
    fl = lab.load_flows(since=keep[0])
    X = FT.make(A, fl, lab.load_themes(), seam=False, amt_mp=3)
    days = days or [keep[-1]]
    U = X[X.uni & X.date.isin(days)].drop(columns=["uni"]).reset_index(drop=True)
    attach_transfer(U)
    attach_auction(U)
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
