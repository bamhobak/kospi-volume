# -*- coding: utf-8 -*-
"""⑪ 4차 — 종목당 금액을 올리면 · 대형주 위주로 하면 (2026-10-25 사용자 "최대 몇만원까지 살 수 있는지 · 종목당 금액 올리면 · 대형주 위주").
과거엔 호가 기록이 없어 '19:51~20:00 거래대금의 k%까지만 산다'로 잰다(k = 10·20%). 금액이 그보다 크면 그 종목은 못 산 것으로 본다.
매수가 = 최고가(가장 비싸게 — 큰 주문은 호가를 쓸고 올라가므로 보수적으로) · 평균가 둘 다. 비용 0.23 · 하룻밤.
무리: 상위 절반(시장 대비 2%p↓ · 쉼 · 10종목) / 대형 120(거래대금 상위, 시장 대비 1.5%p↓ · 쉼 · 10종목) / 대형 120(1%p↓)
    python research/nxt_size.py
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
    L = B[(B.hm >= 1951) & (B.hm <= 2000)]
    vw = ((L.c * L.v).groupby([L.t, L.d]).sum() / L.v.groupby([L.t, L.d]).sum().replace(0, np.nan)).rename("vw")
    hi = L[L.v > 0].groupby(["t", "d"]).h.max().rename("hi")
    a10 = (L.c * L.v).groupby([L.t, L.d]).sum().rename("a10")
    Z = X.merge(pd.concat([p50, vw, hi, a10], axis=1).reset_index(), on=["t", "d"], how="inner")
    Z["AH50"] = (Z.p50 / Z.c - 1) * 100; Z["rel"] = Z.AH50 - Z.mkt
    Z["r_vw"] = (Z.o1 / Z.vw - 1) * 100 - CK; Z["r_hi"] = (Z.o1 / Z.hi - 1) * 100 - CK
    big = set(pd.read_parquet(ROOT / "cache" / "toss_kr_1d.parquet").t.unique())
    calm = Z.mkt > -1.0
    groups = [("상위 절반 · 시장 대비 2%p↓", (Z.rel <= -2) & calm),
              ("대형 120 · 시장 대비 1.5%p↓", Z.t.isin(big) & (Z.rel <= -1.5) & calm),
              ("대형 120 · 시장 대비 1%p↓", Z.t.isin(big) & (Z.rel <= -1.0) & calm)]
    days = sorted(X.d.unique())
    P("# ⑪ 4차 — 종목당 금액 · 대형주 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 금액이 19:51~20:00 거래대금의 k% 를 넘는 종목은 못 산 것으로 뺌 · 하루 10종목(깊은 순, 살 수 있는 것 중) · 칸 = 하루 건수 · 건당 %(최고가 / 평균가) · 연 손익(만원, 최고가 기준)"); P("")
    n = 0
    for gl, gm in groups:
        P("## %s" % gl); P("")
        P("| 종목당 | 거래대금의 | %s | %s |" % (PER[0][0], PER[1][0])); P("|---|---|---|---|")
        G = Z[gm]
        P("| (참고) 마지막 10분 거래대금 중앙 | | %.1f억 | %.1f억 |" % tuple(G[(G.d >= a) & (G.d <= b)].a10.median() / 1e8 for _, a, b in PER))
        for amt in (100, 300, 500, 1000, 2000, 3000):
            for k in (0.1, 0.2):
                n += 1
                z = G[G.a10 * k >= amt * 1e4].sort_values("rel").groupby("d").head(10)
                cells = []
                for _, a, b in PER:
                    dd = [d for d in days if a <= d <= b]
                    q = z[z.d.isin(dd)]
                    if len(q) < 10: cells.append("%d건" % len(q)); continue
                    yr = q.r_hi.sum() * amt / 100 / len(dd) * 250
                    cells.append("%.1f건 · %+.2f / %+.2f · 승률 %d%% · **연 %+.0f만**" % (len(q) / len(dd), q.r_hi.mean(), q.r_vw.mean(), (q.r_hi > 0).mean() * 100, yr))
                P("| %d만 | %d%% | %s | %s |" % (amt, k * 100, cells[0], cells[1]))
        P("")
    P("(칸 %d · %.1f분)" % (n, (time.time() - t0) / 60))
    log_trials("nxt_size_%s" % time.strftime("%Y%m%d"), n)
    (ROOT / "reports" / ("nxt_size_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
