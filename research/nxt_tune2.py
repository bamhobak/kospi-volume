# -*- coding: utf-8 -*-
"""⑪ 10차 — 계좌 크기(3천·5천·1억·1.5억)별 세부값 다시 고르기 (2026-10-25 사용자 "1억 5천만 투자금으로도 비교 가능?").
8차(nxt_tune.py)와 같되 ① 다음 행 ≠ 다음 거래일 줄 빼기(9차에서 찾은 버그) ② 1.5억 계좌 ③ 상한 5천·7천만·k 7% 까지.
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
    X["o1"] = X.groupby("t").o.shift(-1); X["d1"] = X.groupby("t").d.shift(-1)
    cal = sorted(D.d.unique()); nxt = dict(zip(cal, cal[1:]))
    X = X[X.d1 == X.d.map(nxt)].dropna(subset=["o1"]).copy()          # 다음 행이 달력 다음 거래일인 것만(10-25 버그)
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
    S0 = Z[(Z.rel <= -2) & (Z.mkt > -1) & (Z.v41 >= 1e7)].dropna(subset=["g_vw", "g_hi", "a10"]).sort_values(["d", "rel"]).reset_index(drop=True)
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

    # 1차(k 3·5·10%, 천장 10·15%)에서 1등이 모두 k 3%(끝값) · 천장은 안 닿아 같음 → k 를 1·2·3·5% 로 넓히고 천장은 10% 하나(10-25)
    grid = list(itertools.product((-2.0, -2.5, -3.0), MULT, (0.01, 0.02, 0.03, 0.05, 0.07), (500, 1000, 2000, 3000, 5000, 7000), (0.10,), (1e7, 3e7)))
    P("# ⑪ 10차 — 계좌 크기별 세부값(버그 고침 · 1.5억) · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 2025 로 고르고 2026 은 확인만 · 조합 %d개 × 계좌 4 · 연 손익 = 시장충격 뒤(괄호 최고가 매수) · 낙폭 = 시장충격 뒤 최대 낙폭" % len(grid)); P("")
    n = 0
    for capm_acct in (3000, 5000, 10000, 15000):
        capw = capm_acct * 1e4
        res = []
        for g in grid:
            n += 1
            a = sim(capw, *g, D25)
            if not a: continue
            res.append((g, a))
        ok = [(g, a) for g, a in res if a["yr_hi"] > 0 and -a["mdd"] <= capm_acct * 0.30]
        ok.sort(key=lambda x: -x[1]["yr"])
        cur = {3000: (-2.0, "1·2·3", 0.02, 3000, 0.10, 1e7), 5000: (-2.0, "1·2·3", 0.03, 2000, 0.10, 1e7), 10000: (-3.0, "1·1.5·2", 0.05, 3000, 0.10, 1e7),
               15000: (-3.0, "1·1.5·2", 0.05, 3000, 0.10, 1e7)}[capm_acct]          # 지금 추천(8차) — 1.5억은 1억 설정 그대로 비교
        P("## 계좌 %s (2025 조건 통과 %d / %d)" % ("%d만" % capm_acct if capm_acct < 10000 else ("1억" if capm_acct == 10000 else "1.5억"), len(ok), len(res))); P("")
        P("| 순위 | 문턱 | 배율 | 기본 k | 상한 | 천장 | 최소 거래대금 | 2025 연(최고가) · 낙폭 · 건당 · 승률 · 하루 건수/평균 투입 | **2026 확인** 연(최고가) · 낙폭 · 건당 |"); P("|---|---|---|---|---|---|---|---|---|")
        show = ok[:5] + [(cur, sim(capw, *cur, D25))]
        for i, (g, a) in enumerate(show):
            b = sim(capw, *g, D26)
            lab = "8차 추천" if i == len(show) - 1 else str(i + 1)
            P("| %s | %.1f%%p | %s | %d%% | %d만 | %d%% | %d천만 | %+.0f만(%+.0f) · %+.0f · %+.2f%% · %.0f%% · %.1f/%.0f만 | **%+.0f만**(%+.0f) · %+.0f · %+.2f%% |" % (
                lab, g[0], g[1], g[2] * 100, g[3], g[4] * 100, g[5] / 1e7, a["yr"], a["yr_hi"], a["mdd"], a["per"], a["win"], a["n"], a["used"],
                b["yr"], b["yr_hi"], b["mdd"], b["per"]))
        P("")
    P("(칸 %d · %.1f분)" % (n, (time.time() - t0) / 60))
    log_trials("nxt_tune2_%s" % time.strftime("%Y%m%d"), n)
    (ROOT / "reports" / ("nxt_tune2_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
