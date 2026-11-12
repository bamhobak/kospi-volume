# -*- coding: utf-8 -*-
"""대량 그림자 리그 — 데이 후보를 사전 등록해 두고 돈 없이 매일 채점 (2026-11-12 사용자 "기억 rulefind-1112 5번").

원칙: 후보·문턱·채점 방식은 이 파일에 **시작 전에** 적어 두고 바꾸지 않는다(바꾸면 START 를 새로). 미래가 검증 구간.
  · 채점 = 매수 날 1분봉(data/m1/KR/day) 거래량>0 첫 봉 시가 → 마지막 봉 종가, 비용 0.23 + 체결 손해(0.143+1.321√p, 100만 원 가정)
  · 합격선은 후보 수만큼 올림: 날 바구니 평균 > 0 이고 다중검정 DSR(N = 후보 수) ≥ 0.9, 그리고 픽 있는 날 NEED 일 이상
  · 판정은 research/prereg/judge.py 의 'league' 검사가 부른다(매일 21:10, 새 예약 작업 없음)
후보 묶음
  CM*: H0411 반대매매 발동 가격 지도 — 지도 모델(신규 신용을 그날 종가 칸에 쌓고 상환 비례로 빼고, 담보 선 k×(1−0.4)×칸 가격을 종가가 깨면
       그 칸을 강제 물량으로 셈) · F = 강제 물량×종가 ÷ 20일 거래대금 · 사건 날 D → D+2 시가 갭 문턱 이하면 시가 매수 → 종가
       k 1.3/1.4 × 신용 지연 L 3/5 × F 0.5/1/2 × 갭 -1/-2% = 24개
    python research/league/league.py run            # START 뒤 새 날 채점 → data/league/picks.csv·daily.csv
    python research/league/league.py back 120       # 검증용: 최근 120거래일 되짚기(→ data/league/back_*.csv, 판정엔 안 씀)
    python research/league/league.py status         # 후보별 지금 성적
"""
import os, sys, json, math, sqlite3, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; RES = HERE.parent; BASE = RES.parent
sys.path[:0] = [str(RES), str(RES / "factory"), str(BASE)]
if sys.stdout is not None: sys.stdout.reconfigure(encoding="utf-8")
OUT = BASE / "data" / "league"; OUT.mkdir(parents=True, exist_ok=True)
M1 = BASE / "data" / "m1" / "KR" / "day"
START = "20261113"
NEED = 30                                   # 픽 있는 날 수
COST, AMT, IMP_A, IMP_B = 0.23, 100e4, 0.143, 1.321
NB, LG = 820, np.log(1.02)

CANDS = []
for k in (1.3, 1.4):
    for L in (3, 5):
        for F in (0.5, 1.0, 2.0):
            for g in (-1.0, -2.0):
                CANDS.append(dict(id="CM_k%.1f_L%d_F%.1f_g%d" % (k, L, F, int(g)), grp="CM", k=k, L=L, F=F, g=g))


def cohort_events(k, L, since_idx, cal, tk, CL, NW, RD, RM, CC, amt20, base_ok, sp):
    """지도 모델 — since_idx 이후 날의 (날 인덱스, 종목 인덱스, F) 사건."""
    nd, nt = CL.shape
    ar = np.arange(NB, dtype=np.int32)
    bidx = lambda p: np.clip(np.round(np.log(np.maximum(p, 1)) / LG), 0, NB - 1).astype(np.int32)
    S = np.zeros((nt, NB), np.float32); init = np.zeros(nt, bool); ev = []
    for i in range(nd):
        j = i - L
        if j >= 0:
            rm, nw, rd, cc = RM[j], NW[j], RD[j], CC[j]
            ok = np.isfinite(rm) & np.isfinite(cc) & (cc > 0)
            ni = ok & ~init
            if ni.any():
                r_ = np.nonzero(ni)[0]; S[r_, bidx(cc[r_])] += rm[r_]; init |= ni
            up = np.nonzero(ok & init & ~ni)[0]
            if len(up) and j >= 1:
                pv = RM[j - 1][up]
                ratio = np.where(np.isfinite(pv) & (pv > 0), 1 - np.nan_to_num(rd[up]) / np.where(pv > 0, pv, 1), 1.0)
                S[up] *= np.clip(ratio, 0, 1)[:, None]
                S[up, bidx(cc[up])] += np.nan_to_num(nw[up])
            rs = np.nonzero(sp[j] & ok)[0]
            if len(rs): S[rs] = 0; S[rs, bidx(cc[rs])] = rm[rs]
        c_ = CL[i]; v = np.isfinite(c_) & (c_ > 0) & init
        if not v.any(): continue
        tb = np.floor(np.log(np.where(v, c_, 1) / (k * 0.6)) / LG).astype(np.int32)
        mk = (ar[None, :] > tb[:, None]) & v[:, None]
        fs = (S * mk).sum(1); S[mk] = 0
        if i >= since_idx:
            val = fs * c_
            hit = np.nonzero((val >= 1e8) & base_ok[i])[0]
            for t in hit: ev.append((i, t, float(val[t] / amt20[i, t]) if amt20[i, t] > 0 else np.nan))
    return ev


def load():
    import common as C
    c = sqlite3.connect(f"file:{BASE / 'data' / 'kis' / 'market.db'}?mode=ro", uri=True)
    K = pd.read_sql("select date, ticker, close, volume, loan_new, loan_rdmp, loan_rmnd from credit where date >= '20080101'", c); c.close()
    P = pd.read_pickle(C.CACHE / "factory_px.pkl")[["ticker", "date", "close"]]
    P = P[P.date >= "20090101"]
    # 1분봉 날 파일로 factory_px 뒤의 종가 잇기(패널이 하루 이틀 늦다)
    last = P.date.max()
    extra = []
    for f in sorted(M1.glob("*.parquet")):
        if f.stem <= last: continue
        d = pd.read_parquet(f, columns=["t", "c", "v"])
        d = d[d.v > 0].groupby("t").c.last().reset_index().rename(columns={"t": "ticker"}); d["date"] = f.stem
        extra.append(d)
    if extra: P = pd.concat([P] + extra, ignore_index=True)
    cal = sorted(P.date.unique()); tk = sorted(set(K.ticker) & set(P.ticker))
    w = lambda df, col: df.drop_duplicates(["date", "ticker"], keep="last").pivot(index="date", columns="ticker", values=col).reindex(index=cal, columns=tk).values.astype(np.float32)
    CL = w(P, "close"); K = K[K.ticker.isin(tk)]
    NW, RD, RM, CC, VO = (w(K, x) for x in ("loan_new", "loan_rdmp", "loan_rmnd", "close", "volume"))
    rr = CL[1:] / CL[:-1]
    sp = np.zeros_like(CL, dtype=bool); sp[1:] = (rr > 1.42) | (rr < 0.58)
    blk = pd.DataFrame(sp).rolling(60, min_periods=1).max().values.astype(bool)
    amt20 = pd.DataFrame(np.nan_to_num(CC) * np.nan_to_num(VO)).replace(0, np.nan).rolling(20, min_periods=10).mean().ffill(limit=5).values.astype(np.float32)
    base_ok = (CL >= 1000) & (amt20 >= 3e8) & ~blk
    return cal, tk, CL, NW, RD, RM, CC, amt20, base_ok, sp


def m1_oc(day):
    f = M1 / ("%s.parquet" % day)
    if not f.exists(): return None
    d = pd.read_parquet(f, columns=["t", "o", "c", "v"]); d = d[d.v > 0]
    g = d.groupby("t")
    return pd.DataFrame({"o": g.o.first(), "c": g.c.last()})


def score(first_day, tag):
    """first_day 이후 매수 날의 후보별 픽·성적."""
    cal, tk, CL, NW, RD, RM, CC, amt20, base_ok, sp = load()
    cal = np.array(cal)
    # 매수 날 e 에 필요한 사건 날 D = e − 2 거래일. 1분봉 날 파일이 있는 매수 날만.
    days = sorted(p.stem for p in M1.glob("*.parquet") if p.stem >= first_day)
    if not days: print("새 날 없음"); return
    e_idx = [int(np.searchsorted(cal, d)) for d in days if d in set(cal)]
    since = max(min(e_idx) - 2, 0)
    rows = []
    cache = {}
    for (k, L) in sorted({(c["k"], c["L"]) for c in CANDS}):
        ev = cohort_events(k, L, since, cal, tk, CL, NW, RD, RM, CC, amt20, base_ok, sp)
        E = pd.DataFrame(ev, columns=["d", "t", "F"])
        E["e"] = E.d + 2
        E = E[E.e < len(cal)]
        E["day"] = cal[E.e.values]; E["ticker"] = np.array(tk)[E.t.values]; E["prevc"] = CL[E.e.values - 1, E.t.values]
        E["amt20"] = amt20[E.d.values, E.t.values]
        E = E[E.day.isin(days)]
        for day, g in E.groupby("day"):
            if day not in cache: cache[day] = m1_oc(day)
            oc = cache[day]
            if oc is None: continue
            g = g[g.ticker.isin(oc.index)]
            o = oc.o.reindex(g.ticker).values; c_ = oc.c.reindex(g.ticker).values
            gap = (o / g.prevc.values - 1) * 100
            p = AMT / np.where(g.amt20.values > 0, g.amt20.values, np.nan) * 100
            ret = (c_ / o - 1) * 100 - COST - np.maximum(0, IMP_A + IMP_B * np.sqrt(p))
            for c in CANDS:
                if c["k"] != k or c["L"] != L: continue
                m = (g.F.values >= c["F"]) & (gap <= c["g"]) & np.isfinite(ret) & (np.abs(gap) < 29)
                for tt, r_, gg, ff in zip(g.ticker.values[m], ret[m], gap[m], g.F.values[m]):
                    rows.append(dict(cand=c["id"], day=day, ticker=tt, ret=round(float(r_), 3), gap=round(float(gg), 2), F=round(float(ff), 2)))
    R = pd.DataFrame(rows, columns=["cand", "day", "ticker", "ret", "gap", "F"])
    f = OUT / ("picks.csv" if tag == "run" else "back_picks.csv")
    if tag == "run" and f.exists():
        old = pd.read_csv(f, dtype={"day": str, "ticker": str})
        R = pd.concat([old[~old.day.isin(days)], R]).sort_values(["day", "cand"])
    R.to_csv(f, index=False, encoding="utf-8-sig")
    D = R.groupby(["cand", "day"]).ret.agg(["size", "mean"]).reset_index()
    D.to_csv(OUT / ("daily.csv" if tag == "run" else "back_daily.csv"), index=False, encoding="utf-8-sig")
    print("픽", len(R), "· 날", R.day.nunique(), "· 후보", R.cand.nunique())
    return D


def dsr(x, N):
    from verdict import deflated_sharpe
    try: return deflated_sharpe(pd.Series(x), N)["dsr"]
    except Exception: return float("nan")


def status(daily="daily.csv"):
    f = OUT / daily
    if not f.exists(): return []
    D = pd.read_csv(f, dtype={"day": str})
    N = len(CANDS); out = []
    for c in CANDS:
        z = D[D.cand == c["id"]]
        n = len(z); m = float(z["mean"].mean()) if n else float("nan")
        t = float(z["mean"].mean() / z["mean"].std() * math.sqrt(n)) if n > 2 and z["mean"].std() > 0 else float("nan")
        out.append(dict(id=c["id"], days=n, mean=m, t=t, dsr=dsr(z["mean"].values, N) if n >= 12 else float("nan")))
    return out


if __name__ == "__main__":
    a = sys.argv[1:] or ["status"]
    if a[0] == "run": score(START, "run")
    elif a[0] == "back":
        import common as C
        n = int(a[1]) if len(a) > 1 else 120
        days = sorted(p.stem for p in M1.glob("*.parquet"))
        score(days[-n], "back")
        for s in status("back_daily.csv"): print("%-26s 날 %3d 평균 %+.2f t %.1f DSR %.2f" % (s["id"], s["days"], s["mean"], s["t"], s["dsr"]))
    else:
        for s in status(): print(s)
