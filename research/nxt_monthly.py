# -*- coding: utf-8 -*-
"""⑪ 9차 — NXT 장후 빠진 종목(H0366) 월별 수익률·승률 (2026-10-25 사용자 "월별로 체크해볼래").
자료·조건은 nxt_tune.py 와 같다: 시총 상위 절반 · 19:50 장후가 시장 평균보다 2%p↓ · 시장 장후 -1%↓ 날 쉼 · 19:41~50 거래대금 1천만↑
 · 19:51~20:00 VWAP 매수(또는 그 10분 최고가 — 가장 나쁜 체결) → 다음 날 KRX 시가 매도 · 비용 0.23
 ① 건당 — 달마다 건수·평균·중앙·승률 (VWAP / 최고가)
 ② 날 바구니 — 신호 날마다 그날 평균 → 달마다 플러스 날 비율
 ③ 계좌별 추천 설정(nxt_shadow.TUNED: 3천·5천·1억) — 시장충격(√모형) 뒤 달 손익(만원)·계좌 대비 %
    python research/nxt_monthly.py
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
# 10-25 사용자 "1억 5천만도 비교" → research/nxt_tune2.py(버그 고침·1.5억, 2025 로 고름): 1억은 k 7%·상한 5천만으로 바뀜, 1.5억 새로
TUNED = {"3천만": (3000, -2.0, "123", 0.02, 3000), "5천만": (5000, -2.0, "123", 0.03, 2000), "1억": (10000, -3.0, "1152", 0.07, 5000),
         "1.5억": (15000, -2.0, "123", 0.03, 5000),
         # 10-25 사용자 "2억은?" — nxt_tune2.py 20000: 1등 = -3·1·1.5·2·k5%·상한 1억(한 종목에 계좌 절반까지) · 안전판 = 1.5억 설정 그대로(상한 5천만)
         "2억": (20000, -3.0, "1152", 0.05, 10000), "2억 상한5천": (20000, -2.0, "123", 0.03, 5000)}
MULT = {"123": lambda r: np.where(r <= -5, 3.0, np.where(r <= -3, 2.0, 1.0)), "1152": lambda r: np.where(r <= -5, 2.0, np.where(r <= -3, 1.5, 1.0))}


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
    # ⚠ 10-25: 그 종목 1분봉 요약에 빠진 날이 있으면 '다음 행' 이 다음 거래일이 아니다(005810 2026-04-08 → 한참 뒤 시가 -23.6%).
    #   다음 행 날짜가 달력상 바로 다음 거래일인 것만 쓴다. nxt_tune·nxt_capital 등 앞선 실측도 같은 함정이 있었다.
    cal = sorted(D.d.unique()); nxt = dict(zip(cal, cal[1:]))
    bad = X.o1.notna() & (X.d1 != X.d.map(nxt))
    print("다음 날 아닌 '다음 행' %d줄 뺌(전체 %d)" % (bad.sum(), X.o1.notna().sum()))
    X = X[~bad].dropna(subset=["o1"]).copy()
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
    days = sorted(X.d.unique())
    S0 = Z[(Z.rel <= -2) & (Z.mkt > -1) & (Z.v41 >= 1e7)].dropna(subset=["g_vw", "g_hi", "a10"]).sort_values(["d", "rel"]).reset_index(drop=True)
    S0["m"] = S0.d.str[:6]
    P("# ⑪ 9차 — NXT 장후 빠진 종목 월별 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("자료 %s~%s · 거래일 %d · 신호 %d건(%d날) · 비용 %.2f 뒤 %% · 다음 행이 다음 거래일 아닌 줄 %d 뺌" % (days[0], days[-1], len(days), len(S0), S0.d.nunique(), CK, int(bad.sum()))); P("")
    mdays = pd.Series(days).groupby(pd.Series(days).str[:6]).size()
    calm = X.groupby("d").mkt.first()
    rest = (calm <= -1).groupby(calm.index.str[:6]).sum()

    P("## ① 건당 · ② 날 바구니"); P("")
    P("| 달 | 거래일 | 쉰 날(시장 -1%↓) | 신호 날 | 건수 | VWAP 평균 | 중앙 | 승률 | 최고가 매수 평균 | 승률 | 날 바구니 평균 | 플러스 날 |")
    P("|---|---|---|---|---|---|---|---|---|---|---|---|")
    day = S0.groupby("d").agg(vw=("g_vw", "mean"), hi=("g_hi", "mean"))
    day["m"] = day.index.str[:6]
    for m, q in S0.groupby("m"):
        dq = day[day.m == m]
        P("| %s-%s | %d | %d | %d | %d | %+.2f | %+.2f | %.0f%% | %+.2f | %.0f%% | %+.2f | %.0f%% |" % (
            m[:4], m[4:], mdays.get(m, 0), rest.get(m, 0), q.d.nunique(), len(q), q.g_vw.mean(), q.g_vw.median(), (q.g_vw > 0).mean() * 100,
            q.g_hi.mean(), (q.g_hi > 0).mean() * 100, dq.vw.mean(), (dq.vw > 0).mean() * 100))
    a = S0
    P("| **전체** | %d | %d | %d | %d | %+.2f | %+.2f | %.0f%% | %+.2f | %.0f%% | %+.2f | %.0f%% |" % (
        len(days), (calm <= -1).sum(), a.d.nunique(), len(a), a.g_vw.mean(), a.g_vw.median(), (a.g_vw > 0).mean() * 100,
        a.g_hi.mean(), (a.g_hi > 0).mean() * 100, day.vw.mean(), (day.vw > 0).mean() * 100))
    mm = S0.groupby("m").g_vw.mean()
    P(""); P("VWAP 기준 플러스 달 %d/%d · 최고가 기준 플러스 달 %d/%d" % ((mm > 0).sum(), len(mm), (S0.groupby("m").g_hi.mean() > 0).sum(), len(mm)))

    P(""); P("## ③ 계좌별 추천 설정 — 달 손익(시장충격 뒤, 만원) · 계좌 대비"); P("")
    cols = []
    res = {}
    for nm, (capm_acct, rel, mk, k, capm) in TUNED.items():
        capw = capm_acct * 1e4
        z = S0[S0.rel <= rel].copy()
        mlt = MULT[mk](z.rel.values)
        want = np.minimum(np.minimum(capm * 1e4 * mlt, k * z.v41.values * mlt), 0.10 * z.v41.values)
        ok = want >= 30e4; z = z[ok]; want = want[ok]
        cum = pd.Series(want, index=z.index).groupby(z.d.values).cumsum().values
        amt = np.clip(capw - (cum - want), 0, want)
        ok = amt >= 30e4; z = z[ok]; amt = amt[ok]
        r = z.g_vw.values - impact(amt, z.a10.values)
        z = z.assign(pnl=r / 100 * amt / 1e4, amt=amt / 1e4, r=r)
        res[nm] = (z, capm_acct)
        cols.append(nm)
    P("| 달 | " + " | ".join("%s 손익 · 계좌 대비 · 건 · 승률" % c for c in cols) + " |"); P("|---|" + "---|" * len(cols))
    for m in sorted(S0.m.unique()):
        cells = []
        for nm in cols:
            z, cap = res[nm]; q = z[z.m == m]
            cells.append("%+.0f만 · %+.1f%% · %d · %.0f%%" % (q.pnl.sum(), q.pnl.sum() / cap * 100, len(q), (q.r > 0).mean() * 100 if len(q) else 0))
        P("| %s-%s | %s |" % (m[:4], m[4:], " | ".join(cells)))
    cells = []
    for nm in cols:
        z, cap = res[nm]; pm = z.groupby("m").pnl.sum()
        cells.append("%+.0f만 · %+.1f%% · 플러스 달 %d/%d" % (z.pnl.sum(), z.pnl.sum() / cap * 100, (pm > 0).sum(), len(pm)))
    P("| **합계** | %s |" % " | ".join(cells))
    P(""); P("| 계좌 | 한 종목 최대 금액 | 하루 최대 투입 | 위 10건 몫 | 위 10건 빼면 | 가장 나쁜 날 |"); P("|---|---|---|---|---|---|")
    for nm in cols:
        z, cap = res[nm]; zs = z.pnl.sort_values(ascending=False); dp = z.groupby("d").pnl.sum()
        P("| %s | %.0f만 | %.0f만 | %.0f%% | %+.0f만 | %s %+.0f만 |" % (nm, z.amt.max(), z.groupby("d").amt.sum().max(), zs.head(10).sum() / zs.sum() * 100,
                                                       zs.sum() - zs.head(10).sum(), dp.idxmin(), dp.min()))
    P(""); P("## ⑤ 실제로 살 수 있나 — 내 금액 ÷ 19:51~20:00 실제 거래대금(그 10분 동안 모든 사람이 사고판 금액)")
    P("호가창(매도벽) 과거 자료는 없다 — 대신 '그 10분 거래 중 내 몫'. 10%↑면 내가 값을 밀어 올리고, 50%↑면 사실상 그 10분 매도 물량을 혼자 다 받아야 한다.")
    P(""); P("| 계좌 | 건 | 내 몫 중앙 | 90% 선 | 10%↑ 건 | 30%↑ 건 | 50%↑ 건 | 100%↑ 건 | 50%↑ 건 수익(충격 뒤) |"); P("|---|---|---|---|---|---|---|---|---|")
    for nm in cols:
        z, cap = res[nm]; sh = z.amt * 1e4 / z.a10 * 100
        P("| %s | %d | %.1f%% | %.0f%% | %.0f%% | %.0f%% | %.0f%% | %.0f%% | %+.2f%% |" % (nm, len(z), sh.median(), sh.quantile(0.9), (sh >= 10).mean() * 100, (sh >= 30).mean() * 100,
                                                                    (sh >= 50).mean() * 100, (sh >= 100).mean() * 100, z[sh >= 50].r.mean() if (sh >= 50).any() else float("nan")))
    z, cap = res["3천만"]
    P(""); P("참고: 신호 종목의 19:51~20:00 거래대금 중앙 %.1f억 · 하위 25%% %.2f억 · 19:41~50 거래대금 중앙 %.1f억" % (S0.a10.median() / 1e8, S0.a10.quantile(0.25) / 1e8, S0.v41.median() / 1e8))
    P(""); P("가장 나쁜 날(계좌별): " + " · ".join("%s %s %+.0f만" % (nm, *res[nm][0].groupby("d").pnl.sum().agg(["idxmin", "min"]).values) for nm in cols))
    P(""); P("## ④ 큰 몇 건에 기대나 — 3천만 설정")
    z, cap = res["3천만"]
    zs = z.sort_values("pnl", ascending=False)
    tot = z.pnl.sum()
    P("총 %+.0f만 · 위 10건 %+.0f만(%.0f%%) · 위 1%%(%d건) %+.0f만 · 위 10건 빼면 %+.0f만 · 아래 10건 %+.0f만" % (
        tot, zs.pnl.head(10).sum(), zs.pnl.head(10).sum() / tot * 100, max(1, len(z) // 100), zs.pnl.head(max(1, len(z) // 100)).sum(),
        tot - zs.pnl.head(10).sum(), zs.pnl.tail(10).sum()))
    P(""); P("| 날 | 종목 | 시장 대비 | 19:51~20:00 VWAP | 다음 날 시가 | 수익(충격 뒤) | 금액(만) | 손익(만) |"); P("|---|---|---|---|---|---|---|---|")
    for x in pd.concat([zs.head(12), zs.tail(8)]).itertuples():
        P("| %s | %s | %+.1f | %s | %s | %+.1f%% | %.0f | %+.0f |" % (x.d, x.t, x.rel, f"{x.vw:,.0f}", f"{x.o1:,.0f}", x.r, x.amt, x.pnl))
    w = z[z.d == "20260408"]
    P(""); P("2026-04-08(가장 나쁜 날) %d건 · 평균 %+.2f%% · 시장 장후 %+.2f%%" % (len(w), w.r.mean(), w.mkt.iloc[0] if len(w) else 0))
    P(""); P("%.1f분" % ((time.time() - t0) / 60))
    log_trials("nxt_monthly_20261025", 3)
    (ROOT / "reports" / "nxt_monthly_20261025.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
