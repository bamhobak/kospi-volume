# -*- coding: utf-8 -*-
"""⑪ 3차 — NXT 장후 빠진 종목 → 다음 날 KRX 시가, **시총 상위 절반**으로 넓히고 '골고루·안정' 조건 찾기 (2026-10-25 사용자).
유니버스: 달마다 그 달 첫 거래일 kr_scan 시가총액 상위 50%(ETF·우선주 빼고, kr_scan 이 끝난 2026-08 뒤는 08 순위). NXT 미거래 종목은 장후 0 이라 저절로 빠진다.
자료: 토스 통합 일봉(cache/toss_kr_1d_wide.parquet) · 장후 1분봉(cache/ah_m1.parquet 에 덧붙임 — 일봉 장후 ≤ -0.7% 또는 시장 대비 ≤ -0.7%p 인 날)
신호(19:50): AH50 = 19:50 봉 종가/KRX 종가-1 · rel = AH50 - 그날 유니버스 토스 종가 장후 평균(20:00 값 — 약간 앞 봄, 표에 밝힘)
매수 19:51~20:00 VWAP(또는 최고가) → 다음 날 KRX 시가(1분봉 첫 봉) · 비용 0.23 · 종목당 100만원 · 학습 2025-03~12 / 검증 2026~
    python research/nxt_wide.py
"""
import sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
from verdict import log_trials
import collect_m1 as M
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
CK, AMT = 0.23, 100
PER = (("학습 2025-03~12", "20250301", "20251231"), ("검증 2026~", "20260101", "20991231"))
C1D = ROOT / "cache" / "toss_kr_1d_wide.parquet"
CAH = ROOT / "cache" / "ah_m1.parquet"
NC = [0]


def fetch_1d(sym):
    rows, before = [], None
    for _ in range(3):
        q = dict(symbol=sym, interval="1d", count=200)
        if before: q["before"] = before
        try:
            c = (M.get("/api/v1/candles", **q) or {}).get("candles") or []
        except Exception:
            c = []
        if not c: break
        rows += [(sym, x["timestamp"][:10].replace("-", ""), float(x["closePrice"])) for x in c]
        before = min(x["timestamp"] for x in c)
        if min(r[1] for r in rows) < "20250225": break
    return rows


def fetch_ah(td):
    t, d = td
    b = "%s-%s-%sT20:01:00.000+09:00" % (d[:4], d[4:6], d[6:])
    try:
        c = (M.get("/api/v1/candles", symbol=t, interval="1m", count=200, before=b) or {}).get("candles") or []
    except Exception:
        return [(t, d, -1, np.nan, np.nan, 0.0)]           # 실패 표시 — 다음에 다시
    out = [(t, d, int(x["timestamp"][11:13]) * 100 + int(x["timestamp"][14:16]), float(x["highPrice"]), float(x["closePrice"]), float(x["volume"]))
           for x in c if x["timestamp"][:10].replace("-", "") == d]
    out = [r for r in out if r[2] >= 1541]
    return out or [(t, d, 0, np.nan, np.nan, 0.0)]          # 장후 봉 없음 표시(다시 안 받음)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    K = pd.read_pickle(BASE / "data/kr_scan.pkl")[["ticker", "date", "marcap", "pref"]]
    K = K[K.date >= "20250101"]
    K = K[(K.pref != 1) & K.marcap.notna()] if "pref" in K.columns else K[K.marcap.notna()]
    first = K.groupby(K.date.str[:6]).date.min()
    U = {}
    for ym, d0 in first.items():
        z = K[K.date == d0]
        U[ym] = set(z[z.marcap.rank(ascending=False, pct=True) <= 0.5].ticker)
    lastym = max(U)
    D = pd.read_parquet(ROOT / "cache" / "m1_daysum.parquet")[["t", "d", "o", "c"]]
    D = D[D.d >= "20250301"]
    D["ym"] = D.d.str[:6]
    D = D[[t in U.get(ym, U[lastym]) for t, ym in zip(D.t, D.ym)]]
    tick = sorted(D.t.unique())
    P("# ⑪ 3차 — 시총 상위 절반 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 유니버스 달마다 시총 상위 50%% · 1분봉 있는 종목 %d" % len(tick))

    old = pd.read_parquet(C1D) if C1D.exists() else pd.DataFrame(columns=["t", "d", "tc"])
    if not len(old):
        o120 = ROOT / "cache" / "toss_kr_1d.parquet"
        if o120.exists(): old = pd.read_parquet(o120)[["t", "d", "tc"]]
    need = [t for t in tick if t not in set(old.t)]
    print("토스 일봉 받기 %d종목" % len(need), flush=True)
    rows = []
    with ThreadPoolExecutor(4) as ex:
        for i, r in enumerate(ex.map(fetch_1d, need)):
            rows += r
            if i % 200 == 199: print("  일봉 %d/%d %.0fs" % (i + 1, len(need), time.time() - t0), flush=True)
    T = pd.concat([old, pd.DataFrame(rows, columns=["t", "d", "tc"])], ignore_index=True).drop_duplicates(["t", "d"])
    T.to_parquet(C1D)

    X = D.merge(T, on=["t", "d"]).sort_values(["t", "d"])
    X["o1"] = X.groupby("t").o.shift(-1)
    X = X.dropna(subset=["o1"]).copy()
    X["AHd"] = (X.tc / X.c - 1) * 100
    X["mkt"] = X.groupby("d").AHd.transform("mean")
    X["nxt"] = X.groupby("t").AHd.transform(lambda s: (s.abs() > 1e-9).mean() > 0.3)   # NXT 에서 거래되는 종목
    P("- NXT 거래 종목(장후 움직임 있는 날 30%%↑) %d · 행 %d" % (X[X.nxt].t.nunique(), len(X))); P("")
    cand = X[X.nxt & ((X.AHd <= -0.7) | (X.AHd - X.mkt <= -0.7))][["t", "d"]]
    have = pd.read_parquet(CAH) if CAH.exists() else pd.DataFrame(columns=["t", "d", "hm", "h", "c", "v"])
    have = have[have.hm.astype(float) != -1]
    done = set(zip(have.t, have.d))
    todo = [(t, d) for t, d in zip(cand.t, cand.d) if (t, d) not in done]
    print("장후 1분봉 받기 %d건(있음 %d)" % (len(todo), len(done)), flush=True)
    buf = []
    with ThreadPoolExecutor(4) as ex:
        for i, r in enumerate(ex.map(fetch_ah, todo)):
            buf += r
            if i % 2000 == 1999 or i == len(todo) - 1:
                have = pd.concat([have, pd.DataFrame(buf, columns=have.columns)], ignore_index=True); buf = []
                have.to_parquet(CAH); print("  장후 %d/%d %.0f분" % (i + 1, len(todo), (time.time() - t0) / 60), flush=True)

    B = have[have.hm.astype(float) >= 1541].copy(); B["hm"] = B.hm.astype(int)
    p50 = B[B.hm <= 1950].sort_values("hm").groupby(["t", "d"]).c.last().rename("p50")
    L = B[(B.hm >= 1951) & (B.hm <= 2000)]
    vw = ((L.c * L.v).groupby([L.t, L.d]).sum() / L.v.groupby([L.t, L.d]).sum().replace(0, np.nan)).rename("vw")
    hi = L[L.v > 0].groupby(["t", "d"]).h.max().rename("hi")
    a10 = (L.c * L.v).groupby([L.t, L.d]).sum().rename("a10")
    Z = X.merge(pd.concat([p50, vw, hi, a10], axis=1).reset_index(), on=["t", "d"], how="inner")
    Z["AH50"] = (Z.p50 / Z.c - 1) * 100; Z["rel"] = Z.AH50 - Z.mkt
    Z["r_vw"] = (Z.o1 / Z.vw - 1) * 100 - CK; Z["r_hi"] = (Z.o1 / Z.hi - 1) * 100 - CK
    v120 = D.groupby("t").size()  # 자리
    big = set(pd.read_parquet(ROOT / "cache" / "toss_kr_1d.parquet").t.unique())
    Z["big"] = Z.t.isin(big)
    days = sorted(X.d.unique())

    def stat(z, dd, cap=None, col="r_vw"):
        z = z[z.d.isin(dd)].dropna(subset=[col])
        if cap: z = z.sort_values("rel").groupby("d").head(cap)
        n = z.groupby("d").size().reindex(dd, fill_value=0)
        pnl = (z.groupby("d")[col].sum() * AMT / 100).reindex(dd, fill_value=0)
        if len(z) < 15: return None
        cum = pnl.cumsum(); mdd = (cum - cum.cummax()).min()
        mo = z.groupby(z.d.str[:6])[col].mean()
        act = pnl[n > 0]
        return dict(n=len(z), per=n.mean(), med=n.median(), cov=(n > 0).mean() * 100, mx=n.max(), avg=z[col].mean(),
                    win=(z[col] > 0).mean() * 100, mpos=(mo > 0).mean() * 100, nm=len(mo), yr=pnl.sum() / len(dd) * 250,
                    dwin=(act > 0).mean() * 100 if len(act) else np.nan, worst=pnl.min(), mdd=mdd, sd=act.std() if len(act) > 2 else np.nan)

    def line(lab, z, cap=None):
        NC[0] += 1
        cells = []
        for _, a, b in PER:
            dd = [d for d in days if a <= d <= b]
            s = stat(z, dd, cap); h = stat(z, dd, cap, "r_hi")
            cells.append("—" if s is None else "%.1f/%.0f · %d%% · 최대 %d | **%+.2f** (최고가 %+.2f) · %d%% | 월+ %.0f%% | 연 %+.0f만 · 최악 %+.0f · 낙폭 %+.0f" % (
                s["per"], s["med"], s["cov"], s["mx"], s["avg"], h["avg"] if h else np.nan, s["win"], s["mpos"], s["yr"], s["worst"], s["mdd"]))
        P("| %s | %s | %s |" % (lab, cells[0], cells[1]))

    P("- 칸: 하루 평균/중앙 건수 · 신호 있는 날 % · 하루 최대 | 건당 비용 뒤 %(VWAP, 괄호 최고가) · 승률 | 월별 플러스 비율 | 종목당 100만 연 손익 · 최악의 날 · 최대 낙폭(만원)")
    P("- rel 의 '시장 평균'은 그날 20:00 장후 평균(19:50 시점엔 근사치) — 실전은 19:50 평균으로 바꿔 쓴다"); P("")
    P("| 조건 | 학습 2025-03~12 | 검증 2026~ |"); P("|---|---|---|")
    calm = Z.mkt > -1.0
    liq3, liq10 = Z.a10 >= 3e7, Z.a10 >= 1e8
    grid = [("대형 120 · 시장 대비 1%p↓(2차와 같은 무리)", Z.big & (Z.rel <= -1), None)]
    for th in (1.0, 1.5, 2.0, 3.0):
        grid.append(("상위 절반 · 시장 대비 %.1f%%p↓" % th, Z.rel <= -th, None))
    for th in (1.5, 2.0):
        grid.append(("상위 절반 · 절대 -%.1f%%↓" % th, Z.AH50 <= -th, None))
    for th in (1.5, 2.0):
        for cap in (5, 10):
            grid.append(("상위 절반 · 시장 대비 %.1f%%p↓ · 하루 %d종목(깊은 순)" % (th, cap), Z.rel <= -th, cap))
            grid.append(("　└ + 시장 장후 -1%%↓ 날 쉼", (Z.rel <= -th) & calm, cap))
            grid.append(("　└ + 쉼 + 마지막 10분 3천만↑", (Z.rel <= -th) & calm & liq3, cap))
            grid.append(("　└ + 쉼 + 1억↑", (Z.rel <= -th) & calm & liq10, cap))
    grid.append(("중형만(대형 120 빼고) · 시장 대비 2%%p↓ · 쉼 · 3천만↑ · 10종목", ~Z.big & (Z.rel <= -2) & calm & liq3, 10))
    grid.append(("대형 120 만 · 시장 대비 1.5%%p↓ · 쉼 · 10종목", Z.big & (Z.rel <= -1.5) & calm, 10))
    for lab, m, cap in grid:
        line(lab, Z[m], cap)
    P(""); P("(칸 %d · %.1f분)" % (NC[0], (time.time() - t0) / 60))
    log_trials("nxt_wide_%s" % time.strftime("%Y%m%d"), NC[0])
    (ROOT / "reports" / ("nxt_wide_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
