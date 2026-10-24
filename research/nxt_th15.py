# -*- coding: utf-8 -*-
"""⑪ 8차 — 계좌 크기(3천·5천·1억)별 세부값 고르기 (2026-10-25 사용자 "총 투자금 3천·5천·1억일 때 추천 세부값").
**2025(학습)으로만 고르고 2026(검증)은 확인만** — 고른 기준: 시장충격 뒤 연 손익 최대 · 단 최고가 매수로도 플러스 · 낙폭 ≤ 계좌 30%.
격자: 문턱 rel -2/-2.5/-3 · 배율 없음/1·1.5·2/1·2·3 · 기본 k 3/5/10% · 종목 상한(×배율) 500/1천/2천/3천만 · 천장 10/15% · 최소 거래대금 1천/3천만
공통: 시총 상위 절반 · 시장 장후 -1%↓ 날 쉼 · 19:51~20:00 VWAP 매수 → 다음 날 KRX 시가 · 비용 0.23 · 계좌 안에서 깊은 순 · 30만 미만 안 삼 · 충격 √모형
    python research/nxt_tune.py
"""
import itertools, sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
from verdict import log_trials
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
CK = 0.23


def impact(won, a10):
    p = np.clip(won / np.where(a10 > 0, a10, np.nan), 0, None)
    return np.maximum(0, -0.25 + 2.40 * np.sqrt(p))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    D = pd.read_parquet(ROOT / "cache" / "m1_daysum.parquet")[["t", "d", "o", "c"]]
    D = D[D.d >= "20250301"]
    T = pd.read_parquet(ROOT / "cache" / "toss_kr_1d_wide.parquet")
    X = D.merge(T, on=["t", "d"]).sort_values(["t", "d"])
    X["o1"] = X.groupby("t").o.shift(-1); X = X.dropna(subset=["o1"]).copy()
    X["AHd"] = (X.tc / X.c - 1) * 100; X["mkt"] = X.groupby("d").AHd.transform("mean")
    B = pd.read_parquet(ROOT / "cache" / "ah_m1.parquet"); B = B[B.hm.astype(float) >= 1541].copy(); B["hm"] = B.hm.astype(int)
    p50 = B[B.hm <= 1950].sort_values("hm").groupby(["t", "d"]).c.last().rename("p50")
    E = B[(B.hm >= 1941) & (B.hm <= 1950)]; v41 = (E.c * E.v).groupby([E.t, E.d]).sum().rename("v41")
    L = B[(B.hm >= 1951) & (B.hm <= 2000)]
    vw = ((L.c * L.v).groupby([L.t, L.d]).sum() / L.v.groupby([L.t, L.d]).sum().replace(0, np.nan)).rename("vw")
    hi = L[L.v > 0].groupby(["t", "d"]).h.max().rename("hi")
    a10 = (L.c * L.v).groupby([L.t, L.d]).sum().rename("a10")
    Z = X.merge(pd.concat([p50, v41, vw, hi, a10], axis=1).reset_index(), on=["t", "d"], how="inner")
    Z["rel"] = (Z.p50 / Z.c - 1) * 100 - Z.mkt
    Z["g_vw"] = (Z.o1 / Z.vw - 1) * 100 - CK; Z["g_hi"] = (Z.o1 / Z.hi - 1) * 100 - CK
    S0 = Z[(Z.rel <= -1.5) & (Z.mkt > -1) & (Z.v41 >= 1e7)].dropna(subset=["g_vw", "g_hi", "a10"]).sort_values(["d", "rel"]).reset_index(drop=True)
    days = sorted(X.d.unique())
    D25 = [d for d in days if d <= "20251231"]; D26 = [d for d in days if d >= "20260101"]
    MULT = {"없음": lambda r: np.ones_like(r), "1·1.5·2": lambda r: np.where(r <= -5, 2.0, np.where(r <= -3, 1.5, 1.0)),
            "1·2·3": lambda r: np.where(r <= -5, 3.0, np.where(r <= -3, 2.0, 1.0))}

    def sim(capw, rel, mk, k, capm, ceil, liq, dd):
        z = S0[(S0.rel <= rel) & (S0.v41 >= liq) & S0.d.isin(dd)]
        if z.empty: return None
        m = MULT[mk](z.rel.values)
        want = np.minimum(np.minimum(capm * 1e4 * m, k * z.v41.values * m), ceil * z.v41.values)
        ok = want >= 30e4
        z = z[ok]; want = want[ok]
        cum = pd.Series(want, index=z.index).groupby(z.d.values).cumsum().values
        amt = np.clip(capw - (cum - want), 0, want)
        ok = amt >= 30e4
        z = z[ok]; amt = amt[ok]
        if len(z) < 20: return None
        r_im = z.g_vw.values - impact(amt, z.a10.values)
        out = {}
        for nm, r in (("im", r_im), ("hi", z.g_hi.values)):
            pnl = pd.Series(r / 100 * amt).groupby(z.d.values).sum().reindex(dd, fill_value=0) / 1e4
            c = pnl.cumsum()
            out[nm] = (pnl.sum() / len(dd) * 250, (c - c.cummax()).min())
        return dict(yr=out["im"][0], mdd=out["im"][1], yr_hi=out["hi"][0], n=len(z) / len(dd), per=(r_im * amt).sum() / amt.sum(),
                    win=(r_im > 0).mean() * 100, used=pd.Series(amt).groupby(z.d.values).sum().mean() / 1e4)

    n = 0
    P("# ⑪ 9차 — 문턱 -1.5%%p 는? · %s" % time.strftime("%Y-%m-%d")); P("")
    P("## 깊이 구간별 건당 — 금액 min(2천만, 거래대금 3%) 배율 없음 · 평균가+시장충격 (최고가는 충격 없이 최고가 매수)"); P("")
    P("| 시장 대비 | 2025 건수 · 건당(충격) · 최고가 · 승률 | 2026 건수 · 건당(충격) · 최고가 · 승률 |"); P("|---|---|---|")
    amt0 = np.minimum(2000e4, 0.03 * S0.v41.values)
    S0["r_im0"] = S0.g_vw.values - impact(amt0, S0.a10.values)
    for lo, hi_ in ((-2, -1.5), (-2.5, -2), (-3, -2.5), (-100, -3)):
        n += 1
        cells = []
        for dd in (D25, D26):
            z = S0[S0.d.isin(dd) & (S0.rel > lo) & (S0.rel <= hi_)]
            cells.append("%d · %+.2f%% · %+.2f%% · %d%%" % (len(z), z.r_im0.mean(), z.g_hi.mean(), (z.r_im0 > 0).mean() * 100))
        P("| %s | %s | %s |" % (("%.1f ~ %.1f%%p" % (hi_, lo)) if lo > -100 else "-3%p↓", cells[0], cells[1]))
    P("")
    REC = {"3천만": (3000, "1·2·3", 0.02, 3000), "5천만": (5000, "1·2·3", 0.03, 2000), "1억": (10000, "1·1.5·2", 0.05, 3000)}
    for acct, (cm, mk, k, capm) in REC.items():
        P("## 계좌 %s — 배율 %s · k %d%% · 상한 %d만 · 최소 1천만 고정, 문턱만 바꿈" % (acct, mk, k * 100, capm)); P("")
        P("| 문턱 | 2025 연(최고가) · 낙폭 · 건당 · 승률 · 하루 건수 | 2026 연(최고가) · 낙폭 · 건당 |"); P("|---|---|---|")
        for th in (-1.5, -2.0, -2.5, -3.0):
            n += 1
            a = sim(cm * 1e4, th, mk, k, capm, 0.10, 1e7, D25); b = sim(cm * 1e4, th, mk, k, capm, 0.10, 1e7, D26)
            P("| %.1f%%p | %+.0f만(%+.0f) · %+.0f · %+.2f%% · %.0f%% · %.1f | %+.0f만(%+.0f) · %+.0f · %+.2f%% |" % (
                th, a["yr"], a["yr_hi"], a["mdd"], a["per"], a["win"], a["n"], b["yr"], b["yr_hi"], b["mdd"], b["per"]))
        P("")
    P("(칸 %d · %.1f분)" % (n, (time.time() - t0) / 60))
    log_trials("nxt_th15_%s" % time.strftime("%Y%m%d"), n)
    (ROOT / "reports" / ("nxt_th15_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
