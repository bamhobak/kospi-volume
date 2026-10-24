# -*- coding: utf-8 -*-
"""⑪ 7차 — 계좌 크기 안에서 깊은 순으로 채우기(제한 없음 · 계단 배율 · 천장 10%) (2026-10-25 사용자).
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
    P("# ⑪ 7차 — 계좌 크기 안에서 깊은 순 · 계단 배율 1·2·3배 · 천장 10%% · %s" % time.strftime("%Y-%m-%d")); P("")
    S["mult"] = np.where(S.rel <= -5, 3.0, np.where(S.rel <= -3, 2.0, 1.0))
    S["want"] = np.minimum(np.minimum(1000e4 * S.mult, 0.05 * S.v41 * S.mult), 0.10 * S.v41)
    S = S[S.want >= 30e4].sort_values(["d", "rel"])
    big = set(pd.read_parquet(ROOT / "cache" / "toss_kr_1d.parquet").t.unique())       # 대형 120(최근 60일 거래대금 상위)
    S["big"] = S.t.isin(big)
    n = 0
    # 10-25 사용자 "대형주 외는 빼고 대형주만 사는 게 좋을까?" — 무리 셋을 같은 잣대로
    for gl, gm in (("전부(시총 상위 절반)", None), ("대형 120 만", True), ("대형 빼고(중형만)", False)):
      for lab, a, b in PER:
        dd = [d for d in days if a <= d <= b]
        P("## %s · %s (%d거래일)" % (gl, lab, len(dd))); P("")
        P("| 계좌 | 하루 건수 평균 | 연 손익 평균가 / 최고가 / **충격**(만원) | 계좌 대비 연(충격) | 건당(충격) | 승률 | 낙폭(충격) | 버는 날 |"); P("|---|---|---|---|---|---|---|---|")
        for capm in (1000, 3000, 5000, 10000, 30000, None):
            n += 1
            z = S[S.d.isin(dd) & ((S.big == gm) if gm is not None else True)].copy()
            if capm:
                z["cum"] = z.groupby("d").want.cumsum()
                z["amt"] = np.clip(capm * 1e4 - (z.cum - z.want), 0, z.want)
            else:
                z["amt"] = z.want
            z = z[z.amt >= 30e4]
            z["r_im"] = z.g_vw - impact(z.amt, z.a10)
            pn = [((z[c] / 100 * z.amt).groupby(z.d).sum().reindex(dd, fill_value=0) / 1e4) for c in ("g_vw", "g_hi", "r_im")]
            cum = pn[2].cumsum(); mdd = (cum - cum.cummax()).min()
            act = pn[2][z.groupby("d").size().reindex(dd, fill_value=0) > 0]
            yr = [p.sum() / len(dd) * 250 for p in pn]
            P("| %s | %.1f | %+.0f / %+.0f / **%+.0f** | %s | %+.2f%% | %d%% | %+.0f | %d%% |" % (
                ("%d만" % capm) if capm else "제한 없음", z.groupby("d").size().reindex(dd, fill_value=0).mean(), *yr,
                ("%+.0f%%" % (yr[2] / capm * 100)) if capm else "—", (z.r_im * z.amt).sum() / z.amt.sum(), (z.r_im > 0).mean() * 100, mdd, (act > 0).mean() * 100))
        P("")
    P("(칸 %d · %.1f분)" % (n, (time.time() - t0) / 60))
    log_trials("nxt_capital_%s" % time.strftime("%Y%m%d"), n)
    (ROOT / "reports" / ("nxt_capital_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
