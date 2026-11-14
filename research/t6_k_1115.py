# -*- coding: utf-8 -*-
"""2026-11-15 t6_full_1115 덧붙임 — 종목당 비율 k × 상한 × 계좌 격자(새 전 종목 패널, 상위 절반) + 그림자 매수1호가 체결률."""
import sys, runpy
from pathlib import Path
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent
def impact(won, a):
    p = np.clip(won / np.where(a > 0, a, np.nan), 0, None)
    return np.nan_to_num(np.maximum(0, -0.25 + 2.40 * np.sqrt(p)), nan=5.0)
Z = pd.read_pickle(r"C:\temp\kp\t6_full_panel_1115.pkl"); Z = Z[Z.half]
Z = Z[(Z.AH50 <= -2.5) & ~((Z.dayr.abs() <= 1.0).fillna(False))]
OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))


def acct(z, Cap, cap, k, half_imp=False):
    z = z.sort_values(["d", "AH50"]).copy(); z["rk"] = z.groupby("d").cumcount(); z = z[z.rk < 40]
    amt = np.minimum(cap, k * z.v41.values); amt = np.where(amt >= 30e4, amt, 0)
    cum = pd.Series(amt, index=z.index).groupby(z.d.values).cumsum().values
    amt = np.clip(Cap - (cum - amt), 0, amt); amt = np.where(amt >= 30e4, amt, 0); ok = amt > 0; z = z[ok]; amt = amt[ok]
    bi = impact(amt, z.a10.values) * (0.4 if half_imp else 1); si = impact(amt, z.v0f.values)
    pnl = pd.Series(amt * (z.g_vw.values - bi - si) / 100, index=z.index); mp = pnl.groupby(z.m.values).sum(); dp = pnl.groupby(z.d.values).sum()
    return pnl.sum() / 1e4, mp[mp.index < "202601"].mean() / 1e4, mp[mp.index >= "202601"].mean() / 1e4, (mp > 0).sum(), dp.min() / 1e4, amt.mean() / 1e4
P("## 종목당 비율 k × 상한 (20달 합계 만원 · 괄호 = 사는 충격을 그림자 호가 실측처럼 모형의 40%로)\n")
for Cap in (5e7, 1e8, 1.5e8):
    P("\n### 계좌 하룻밤 %g천만\n" % (Cap / 1e7))
    P("| 종목당 상한 | k 3% | k 5% | k 7% | k 10%(지금) | k 15% |"); P("|---|---|---|---|---|---|")
    for cap in (500e4, 1000e4, 1500e4, 3000e4):
        cells = []
        for k in (0.03, 0.05, 0.07, 0.10, 0.15):
            a = acct(Z, Cap, cap, k); b = acct(Z, Cap, cap, k, True)
            cells.append("%+.0f (%+.0f) · %d/20달 · 최악 %+.0f" % (a[0], b[0], a[3], a[4]))
        P("| %d만 | %s |" % (cap / 1e4, " | ".join(cells)))
L = pd.read_csv(ROOT.parent / "data" / "nxt" / "log.csv")
for g in ("live", "picks"):
    x = L[L.grp == g]
    if not len(x): continue
    bf = pd.to_numeric(x.bid_fill, errors="coerce")
    P("\n- 그림자 %s %d건: 매도1호가 매수 건당 %+.2f%% · 매수1호가 지정가(10분 안에 닿으면 체결) 체결률 %.0f%% · 체결된 것 건당 %+.2f%% (같은 건 매도1호가면 %+.2f%%) · 안 닿은 것 매도1호가 건당 %+.2f%%" % (
        g, len(x), x.r_ask.mean(), (bf > 0).mean() * 100 if bf.notna().any() else (x.r_bid.notna().mean() * 100), x.r_bid.mean(), x[x.r_bid.notna()].r_ask.mean(), x[x.r_bid.isna()].r_ask.mean()))
(ROOT / "reports" / "t6_k_1115.md").write_text("\n".join(OUT), encoding="utf-8")
