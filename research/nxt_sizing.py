# -*- coding: utf-8 -*-
"""⑪ 5차 — 거래대금 비례 금액(대형은 많이, 거래 적은 건 적게) · 대형주 종목당 최대 금액 (2026-10-25 사용자).
신호: 시총 상위 절반 · 19:50 시장 장후 평균 대비 2%p↓ · 시장 -1%↓ 날 쉼 · 19:41~19:50 거래대금 1천만↑ · 하루 10종목(깊은 순)
금액: A 모두 100만 / B min(상한, k × 19:41~19:50 거래대금) — k 5·10% · 상한 1천·3천·5천만 · 하한 30만(미만은 안 삼)
체결: 평균가(19:51~20:00 VWAP) · 최고가 · 평균가+시장충격(√ 모형: max(0, -0.25 + 2.40·√(금액 ÷ 19:51~20:00 거래대금)) %, day_exec 와 같은 꼴)
대형 최대 금액: 대형 120(1.5%p↓) 종목당 1천만~1억 고정, 시장충격 넣은 건당.
    python research/nxt_sizing.py
"""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
from verdict import log_trials
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
CK = 0.23
PER = (("학습 2025-03~12", "20250301", "20251231"), ("검증 2026~", "20260101", "20991231"))


def impact(won, a10):
    p = np.clip(won / a10.replace(0, np.nan), 0, None)
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
    Z["AH50"] = (Z.p50 / Z.c - 1) * 100; Z["rel"] = Z.AH50 - Z.mkt
    Z["g_vw"] = (Z.o1 / Z.vw - 1) * 100 - CK; Z["g_hi"] = (Z.o1 / Z.hi - 1) * 100 - CK
    big = set(pd.read_parquet(ROOT / "cache" / "toss_kr_1d.parquet").t.unique())
    days = sorted(X.d.unique())
    S = Z[(Z.rel <= -2) & (Z.mkt > -1) & (Z.v41 >= 1e7)].sort_values("rel").groupby("d").head(10).copy()

    def run(z, amt, dd):
        z = z[z.d.isin(dd)].copy(); z["amt"] = amt.reindex(z.index)
        z = z[z.amt >= 30e4]
        if len(z) < 10: return None
        z["r_im"] = z.g_vw - impact(z.amt, z.a10)
        res = {}
        for col in ("g_vw", "g_hi", "r_im"):
            pnl = (z[col] / 100 * z.amt).groupby(z.d).sum().reindex(dd, fill_value=0) / 1e4
            cum = pnl.cumsum()
            res[col] = (pnl.sum() / len(dd) * 250, (cum - cum.cummax()).min(), (z[col] * z.amt).sum() / z.amt.sum())
        inv = z.groupby("d").amt.sum().reindex(dd, fill_value=0) / 1e4
        return dict(n=len(z) / len(dd), avg_amt=z.amt.mean() / 1e4, med_amt=z.amt.median() / 1e4, big_amt=z[z.t.isin(big)].amt.mean() / 1e4 if z.t.isin(big).any() else 0,
                    inv_max=inv.max(), inv_mean=inv[inv > 0].mean(), part=(z.amt / z.a10).median() * 100, **res)

    P("# ⑪ 5차 — 거래대금 비례 금액 · 대형주 최대 금액 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 신호: 상위 절반 · 시장 대비 2%p↓ · 시장 -1%↓ 날 쉼 · 19:41~19:50 거래대금 1천만↑ · 하루 10종목 — 금액만 바꿔 본다")
    P("- 칸: 연 손익(만원) 평균가 / 최고가 / **평균가+시장충격** · 금액 가중 건당 %(시장충격) · 최대 낙폭(시장충격) · 종목당 평균 금액(대형) · 하루 최대 투입 · 주문 ÷ 마지막 10분 거래대금 중앙"); P("")
    schemes = [("A 모두 100만", lambda z: pd.Series(100e4, index=z.index))]
    for k in (0.05, 0.10):
        for cap in (1000, 3000, 5000):
            schemes.append(("B %d%% × 19:41~50 거래대금 · 상한 %d만" % (k * 100, cap), lambda z, k=k, cap=cap: np.minimum(cap * 1e4, k * z.v41)))
    n = 0
    for lab, a, b in PER:
        dd = [d for d in days if a <= d <= b]
        P("## %s (%d거래일)" % (lab, len(dd))); P("")
        P("| 금액 방식 | 하루 건수 | 연 손익 평균가 / 최고가 / **충격** | 건당(충격) | 낙폭(충격) | 종목당 평균(대형) | 하루 최대 투입 | 주문/10분 |"); P("|---|---|---|---|---|---|---|---|")
        for sl, fn in schemes:
            n += 1
            r = run(S, fn(S), dd)
            if not r: P("| %s | — |" % sl); continue
            P("| %s | %.1f | %+.0f / %+.0f / **%+.0f** | %+.2f%% | %+.0f | %.0f만(%.0f만) | %.0f만 | %.1f%% |" % (
                sl, r["n"], r["g_vw"][0], r["g_hi"][0], r["r_im"][0], r["r_im"][2], r["r_im"][1], r["avg_amt"], r["big_amt"], r["inv_max"], r["part"]))
        P("")
    P("## 대형 120 · 시장 대비 1.5%p↓ · 쉼 · 10종목 — 종목당 고정 금액을 올리면 (시장충격 넣은 건당 %)"); P("")
    G = Z[Z.t.isin(big) & (Z.rel <= -1.5) & (Z.mkt > -1)].sort_values("rel").groupby("d").head(10)
    P("| 종목당 | %s 건당(충격) · 연 손익 | %s 건당(충격) · 연 손익 | 주문/10분 중앙 |" % (PER[0][0], PER[1][0])); P("|---|---|---|---|")
    for amt in (1000, 2000, 3000, 5000, 7000, 10000):
        n += 1
        cells = []
        for _, a, b in PER:
            dd = [d for d in days if a <= d <= b]
            g = G[G.d.isin(dd)]
            r = g.g_vw - impact(pd.Series(amt * 1e4, index=g.index), g.a10)
            cells.append("%+.2f%% · 연 %+.0f만" % (r.mean(), r.sum() * amt / 100 / len(dd) * 250))
        part = (amt * 1e4 / G.a10).median() * 100
        P("| %d만 | %s | %s | %.1f%% |" % (amt, cells[0], cells[1], part))
    P(""); P("(칸 %d · %.1f분)" % (n, (time.time() - t0) / 60))
    log_trials("nxt_sizing_%s" % time.strftime("%Y%m%d"), n)
    (ROOT / "reports" / ("nxt_sizing_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
