# -*- coding: utf-8 -*-
"""2026-11-23 [갭하락] 인버스 ETF 헤지 — 계좌 금액 기준 (gap_hedge_1123.py 뒤이어, H0432).
앞 스크립트는 날마다 '바구니 평균'이라 신호 1개인 날과 45개인 날이 같은 무게였다. 실제 계좌는 건당 같은 금액(30만)이라 신호 많은 날(=시장이 빠진 날)이 훨씬 무겁다.
  하루 손익(만원) = Σ(건별 시가→종가 − 0.23) × 30만 ÷ 100 · 하루 최대 40건(깊은 순) · 헤지 = 그날 산 금액 × 배율만큼 인버스 ETF 시가 매수·종가 매도(왕복 0.05%)
  칸: 코스피200 인버스·코스닥150 인버스·둘 반반 × 0.3·0.5·0.87·1.0 = 12칸 · 학습(2016-08~2022)에서 '최악의 날·낙폭 대비 수익'으로 고르고 검증(2023~)은 그 칸.
    python research/memguard.py research/gap_hedge_1123b.py → research/reports/gap_hedge_1123.md 끝에 덧붙임"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
OUT = []; P = lambda s="": (OUT.append(str(s)), print(s, flush=True))
CK, EC, UNIT, MAXN = 0.23, 0.05, 30.0, 40           # 건당 30만원
T0, TV = "20160811", "20230101"
E = pd.read_parquet(ROOT / "cache" / "inv_etf_1123.parquet"); E["oc"] = (E.c / E.o - 1) * 100
X = E.pivot(index="date", columns="t", values="oc")
U = pd.read_pickle(BASE / "data" / "y1_hist.pkl")
U = U[(U.liq <= 2 / 3) & (U.q_gap <= 0.40) & (U.q_vm.fillna(1) <= 0.30) & (U.rgap <= 3.0)].dropna(subset=["oc", "amt20"])
NC = [0]


def acct(th):
    Z = U[U.rgap <= th].sort_values(["date", "rgap"]); Z = Z[Z.groupby("date").cumcount() < MAXN]
    g = Z.groupby("date").oc
    D = pd.DataFrame({"n": g.size(), "pnl": (g.sum() - CK * g.size()) * UNIT / 100}).join(X, how="inner").dropna(subset=["114800", "251340"]).loc[T0:]
    D["inv"] = D.n * UNIT
    return D


def hedged(D, col, b):
    h = (D["114800"] + D["251340"]) / 2 if col == "mix" else D[col]
    return D.pnl + b * D.inv * (h - EC) / 100


def stat(r):
    cs = r.cumsum(); dd = (cs - cs.cummax()).min(); yrs = len(r) / 245
    mon = r.groupby(r.index.str[:6]).sum()
    return dict(tot=r.sum(), yr=r.sum() / yrs, sd=r.std(), worst=r.min(), q1=r.quantile(0.01), dd=dd, mworst=mon.min(), mwin=(mon > 0).mean() * 100, calmar=(r.sum() / yrs) / abs(dd) if dd < 0 else np.nan)


HEAD = "| 판 | 합(만원) | 1년 평균 | 하루 편차 | 최악의 날 | 하위 1% 날 | 가장 깊은 낙폭 | 최악의 달 | 플러스 달 | 1년 수익÷낙폭 |\n|---|---|---|---|---|---|---|---|---|---|"
line = lambda lab, s: "| %s | %+.0f | %+.0f | %.1f | %+.0f | %+.0f | %.0f | %+.0f | %d%% | %.2f |" % (lab, s["tot"], s["yr"], s["sd"], s["worst"], s["q1"], s["dd"], s["mworst"], s["mwin"], s["calmar"])
HEDGES = [("114800", "코스피200 인버스"), ("251340", "코스닥150 인버스"), ("mix", "둘 반반")]
P("\n---\n\n# 계좌 금액 기준 (건당 30만 · 하루 최대 40건 · 값 만원)\n")
D = acct(-1.5); TR, VA = D.loc[:"20221231"], D.loc[TV:]
P("- 말한 그대로(시장 대비 갭 ≤ -1.5): %d일 · 하루 평균 %.1f건(최대 %d) · 하루 산 금액 평균 %.0f만·최대 %.0f만" % (len(D), D.n.mean(), D.n.max(), D.inv.mean(), D.inv.max()))
for nm, Z in (("학습", TR), ("검증", VA)):
    P("- %s: 하루 손익 × 코스닥150 인버스(금액 가중) 상관 %+.2f · 코스피200 인버스 %+.2f" % (nm, np.corrcoef(Z.pnl, Z.inv * Z["251340"])[0, 1], np.corrcoef(Z.pnl, Z.inv * Z["114800"])[0, 1]))
P("\n## 학습 (2016-08~2022)\n"); P(HEAD); P(line("헤지 없음", stat(TR.pnl)))
best, bk = None, None
for col, en in HEDGES:
    for b in (0.3, 0.5, 0.87, 1.0):
        s = stat(hedged(TR, col, b)); NC[0] += 1; P(line("%s %.2f배" % (en, b), s))
        if best is None or s["calmar"] > best["calmar"]: best, bk = s, (col, en, b)
P("\n학습에서 '1년 수익÷낙폭'이 가장 높은 칸 = **%s %.2f배** → 검증은 이 칸." % (bk[1], bk[2]))
P("\n## 검증 (2023~2026-11-04)\n"); P(HEAD); P(line("헤지 없음", stat(VA.pnl))); P(line("**고른 칸: %s %.2f배**" % (bk[1], bk[2]), stat(hedged(VA, bk[0], bk[2]))))
P("\n참고(검증 나머지 칸 — 고르는 데 안 씀):\n"); P(HEAD)
for col, en in HEDGES:
    for b in (0.3, 0.5, 0.87, 1.0): P(line("%s %.2f배" % (en, b), stat(hedged(VA, col, b))))
H = hedged(D, bk[0], bk[2])
P("\n## 해마다 (헤지 없음 → 고른 칸)\n"); P("| 해 | 합 | 하루 편차 | 최악의 날 | 가장 깊은 낙폭 | 최악의 달 |"); P("|---|---|---|---|---|---|")
yrs = sorted({d[:4] for d in D.index}); cnt = dict(sd=0, worst=0, dd=0, tot=0)
for y in yrs:
    a, b = stat(D.pnl[D.index.str[:4] == y]), stat(H[H.index.str[:4] == y])
    cnt["sd"] += b["sd"] < a["sd"]; cnt["worst"] += b["worst"] > a["worst"]; cnt["dd"] += b["dd"] > a["dd"]; cnt["tot"] += b["tot"] > a["tot"]
    P("| %s | %+.0f → %+.0f | %.1f → %.1f | %+.0f → %+.0f | %.0f → %.0f | %+.0f → %+.0f |" % (y, a["tot"], b["tot"], a["sd"], b["sd"], a["worst"], b["worst"], a["dd"], b["dd"], a["mworst"], b["mworst"]))
P("\n%d해 중: 편차 준 해 %d · 최악의 날 덜 나쁜 해 %d · 낙폭 얕아진 해 %d · 합이 는 해 %d" % (len(yrs), cnt["sd"], cnt["worst"], cnt["dd"], cnt["tot"]))
P("\n## 가장 나빴던 날 15개 (계좌 기준)\n"); P("| 날 | 건수 | 산 금액 | 손익 | 코스닥150 인버스 | 코스피200 인버스 | 고른 칸 헤지 뒤 |"); P("|---|---|---|---|---|---|---|")
for d, r in D.sort_values("pnl").head(15).iterrows(): P("| %s | %d | %.0f | %+.0f | %+.2f%% | %+.2f%% | %+.0f |" % (d, r.n, r.inv, r.pnl, r["251340"], r["114800"], H[d]))
w = D.sort_values("pnl"); P("\n가장 나빴던 30일 합: %+.0f → %+.0f · 가장 좋았던 30일 합: %+.0f → %+.0f · 나머지 날 합: %+.0f → %+.0f" % (
    w.pnl.head(30).sum(), H[w.index[:30]].sum(), w.pnl.tail(30).sum(), H[w.index[-30:]].sum(), w.pnl.iloc[30:-30].sum(), H[w.index[30:-30]].sum()))
P("헤지에 묶이는 돈: 하루 평균 %.0f만 · 최대 %.0f만 (산 금액 × %.2f)" % (D.inv.mean() * bk[2], D.inv.max() * bk[2], bk[2]))
P("\n## 변형 (같은 칸)\n"); P("| 판 | 구간 | 합 | 하루 편차 | 최악의 날 | 가장 깊은 낙폭 | 1년 수익÷낙폭 |"); P("|---|---|---|---|---|---|---|")
for lab, Dv in (("시장 대비 갭 ≤ -1.0", acct(-1.0)), ("시장 대비 갭 ≤ -2.0", acct(-2.0))):
    Hv = hedged(Dv, bk[0], bk[2])
    for nm, sl in (("학습", slice(None, "20221231")), ("검증", slice(TV, None))):
        a, b = stat(Dv.pnl.loc[sl]), stat(Hv.loc[sl]); NC[0] += 1
        P("| %s | %s | %+.0f → %+.0f | %.1f → %.1f | %+.0f → %+.0f | %.0f → %.0f | %.2f → %.2f |" % (lab, nm, a["tot"], b["tot"], a["sd"], b["sd"], a["worst"], b["worst"], a["dd"], b["dd"], a["calmar"], b["calmar"]))
for lab, r in (("신호 10건↑ 날만 헤지", pd.Series(np.where(D.n >= 10, H, D.pnl), index=D.index)), ("ETF 왕복 비용 0.10%", H - bk[2] * D.inv * 0.05 / 100)):
    NC[0] += 1
    for nm, sl in (("학습", slice(None, "20221231")), ("검증", slice(TV, None))):
        a, b = stat(D.pnl.loc[sl]), stat(r.loc[sl])
        P("| %s | %s | %+.0f → %+.0f | %.1f → %.1f | %+.0f → %+.0f | %.0f → %.0f | %.2f → %.2f |" % (lab, nm, a["tot"], b["tot"], a["sd"], b["sd"], a["worst"], b["worst"], a["dd"], b["dd"], a["calmar"], b["calmar"]))
P("\n시험 칸 %d" % NC[0])
f = ROOT / "reports" / "gap_hedge_1123.md"
f.write_text(f.read_text(encoding="utf-8").split("\n---\n\n# 계좌 금액 기준")[0].rstrip("\n") + "\n" + "\n".join(OUT) + "\n", encoding="utf-8")
if "--nolog" not in sys.argv:
    try:
        from verdict import log_trials
        log_trials("gap_hedge_1123", NC[0])
    except Exception as ex: print("칸 수 기록 실패:", repr(ex)[:200])
