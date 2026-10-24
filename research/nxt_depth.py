# -*- coding: utf-8 -*-
"""⑪ 6차 — 하루 종목 수 제한 풀기 · 깊이 배율(갭 하락 조용주처럼 시장 대비 더 빠질수록 더 산다) (2026-10-25 사용자).
신호: 시총 상위 절반 · 19:50 시장 장후 평균 대비 2%p↓ · 시장 -1%↓ 날 쉼 · 19:41~19:50 거래대금 1천만↑ · **종목 수 제한 없음**
금액 기본 = min(1천만, 5% × 19:41~19:50 거래대금)
배율 M1 = clip(-rel/2, 1, 3) · M2 = -2~-3 1배 · -3~-5 2배 · -5↓ 3배 — 금액·상한에 같이 곱함 · 천장(선택) = 10% × 19:41~19:50 거래대금
체결: 평균가 · 최고가 · 평균가+시장충격(√ 모형, nxt_sizing 과 같음) · 비용 0.23
    python research/nxt_depth.py
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
    days = sorted(X.d.unique())
    S = Z[(Z.rel <= -2) & (Z.mkt > -1) & (Z.v41 >= 1e7)].dropna(subset=["g_vw", "g_hi", "a10"]).copy()
    base = np.minimum(1000e4, 0.05 * S.v41)
    S["imb"] = S.g_vw - impact(base, S.a10)

    P("# ⑪ 6차 — 종목 수 제한 풀기 · 깊이 배율 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("## 깊이(시장 대비) 구간별 건당 — 제한 없음, 기본 금액(5%·상한 1천만)"); P("")
    P("| 시장 대비 | %s 건수 · 평균가 / 최고가 / **충격** · 승률 | %s 건수 · 평균가 / 최고가 / **충격** · 승률 |" % (PER[0][0], PER[1][0])); P("|---|---|---|")
    bins = [(-3, -2), (-4, -3), (-5, -4), (-7, -5), (-100, -7)]
    n = 0
    for lo, hi_ in bins:
        n += 1
        cells = []
        for _, a, b in PER:
            z = S[(S.d >= a) & (S.d <= b) & (S.rel > lo) & (S.rel <= hi_)]
            cells.append("%d · %+.2f / %+.2f / **%+.2f** · %d%%" % (len(z), z.g_vw.mean(), z.g_hi.mean(), z.imb.mean(), (z.imb > 0).mean() * 100) if len(z) >= 10 else "%d건" % len(z))
        P("| %d ~ %d%%p | %s | %s |" % (hi_, lo, cells[0], cells[1]) if lo > -100 else "| -7%%p↓ | %s | %s |" % (cells[0], cells[1]))
    P("")

    def m1(r): return np.clip(-r / 2, 1, 3)
    def m2(r): return np.where(r <= -5, 3.0, np.where(r <= -3, 2.0, 1.0))
    variants = [("하루 10종목 제한 · 배율 없음(지난번)", None, False, 10),
                ("제한 없음 · 배율 없음", None, False, None),
                ("제한 없음 · M1 연속 1~3배", m1, False, None),
                ("제한 없음 · M1 · 천장 10%", m1, True, None),
                ("제한 없음 · M2 계단 1·2·3배", m2, False, None),
                ("제한 없음 · M2 · 천장 10%", m2, True, None)]
    for lab, a, b in PER:
        dd = [d for d in days if a <= d <= b]
        P("## %s (%d거래일) — 금액 방식별" % (lab, len(dd))); P("")
        P("| 방식 | 하루 건수 평균/최대 | 연 손익 평균가 / 최고가 / **충격**(만원) | 건당(충격, 금액 가중) | 낙폭(충격) | 하루 최대 투입 | 하루 평균 투입 |"); P("|---|---|---|---|---|---|---|")
        for vl, mf, ceil, cap in variants:
            n += 1
            z = S[S.d.isin(dd)].copy()
            if cap: z = z.sort_values("rel").groupby("d").head(cap)
            mult = mf(z.rel.values) if mf else 1.0
            amt = np.minimum(1000e4 * mult, 0.05 * z.v41 * mult)
            if ceil: amt = np.minimum(amt, 0.10 * z.v41)
            z["amt"] = amt; z = z[z.amt >= 30e4]
            z["r_im"] = z.g_vw - impact(z.amt, z.a10)
            out = []
            for col in ("g_vw", "g_hi", "r_im"):
                pnl = (z[col] / 100 * z.amt).groupby(z.d).sum().reindex(dd, fill_value=0) / 1e4
                out.append(pnl)
            cum = out[2].cumsum(); mdd = (cum - cum.cummax()).min()
            nn = z.groupby("d").size().reindex(dd, fill_value=0)
            inv = z.groupby("d").amt.sum().reindex(dd, fill_value=0) / 1e4
            P("| %s | %.1f / %d | %+.0f / %+.0f / **%+.0f** | %+.2f%% | %+.0f | %.0f만 | %.0f만 |" % (
                vl, nn.mean(), nn.max(), *(o.sum() / len(dd) * 250 for o in out), (z.r_im * z.amt).sum() / z.amt.sum(), mdd, inv.max(), inv[inv > 0].mean()))
        P("")
    P("(칸 %d · %.1f분)" % (n, (time.time() - t0) / 60))
    log_trials("nxt_depth_%s" % time.strftime("%Y%m%d"), n)
    (ROOT / "reports" / ("nxt_depth_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
