# -*- coding: utf-8 -*-
"""2026-11-25 [장후 낙폭] — 낮에 시가 대비 많이 오른 종목을 빼면. 사용자 "장 마감 가격이 그날 시초가 대비 너무 많이 오른 건 빼는 건 어떤지 실측해봐"
  바탕 = 지금 실전 조건(11-05): 장후 등락(19:50 ÷ KRX 종가) ≤ -2.5% · 낮 등락(종가 ÷ 전날 종가) ±1% 안이면 뺌 · 깊은 순 계좌 3천만 · 종목당 min(500만, 19:41~50 거래대금 10%) · 30만 미만 안 삼
  패널 = nxt_grid_1105 의 C:/temp/kp/nxt_full0_panel.pkl(2025-03~2026-10). 손익 = 19:51~20:00 VWAP 매수 → 다음 날 KRX 시가 - 0.23 - 사고·파는 √충격.
  말한 그대로 = oc(KRX 종가 ÷ 그날 KRX 시가 - 1) 가 문턱보다 크면 뺌 · 변형 = dayr(종가 ÷ 전날 종가 - 1) 가 문턱보다 크면 뺌
    python research/memguard.py research/nxt_oc_1125.py → research/reports/nxt_oc_1125.md"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent
OUT = []; P = lambda s="": (OUT.append(str(s)), print(s, flush=True))


def impact(won, a):
    p = np.clip(won / np.where(a > 0, a, np.nan), 0, None)
    return np.maximum(0, -0.25 + 2.40 * np.sqrt(p))


Z = pd.read_pickle(r"C:\temp\kp\nxt_full0_panel.pkl")
cal = sorted(pd.read_parquet(ROOT / "cache/m1_daysum.parquet", columns=["d"]).d.unique()); nx = dict(zip(cal, cal[1:]))
Z["d1"] = Z.d.map(nx)
Z = Z.merge(pd.read_pickle(r"C:\temp\kp\nxt_v0.pkl"), on=["t", "d1"], how="left")
Z["v0f"] = Z.v0.fillna(Z.a10); Z["v41"] = Z.v41.fillna(0)
A = 100e4
Z["r"] = Z.g_vw - impact(A, Z.a10.values) - impact(A, Z.v0f.values)
Z["oc"] = (Z.c / Z.o - 1) * 100
LM = Z.m[Z.d < "20260101"].nunique(); VM = Z.m[Z.d >= "20260101"].nunique()
B = Z[(Z.AH50 <= -2.5) & ~((Z.dayr.abs() <= 1.0).fillna(False))].copy()
B["L"] = B.d < "20260101"
P("# [장후 낙폭] 낮에 많이 오른 종목 빼기 (2026-11-25)\n")
P("- 바탕: 지금 실전 조건 %d건 · %s~%s · %d일 · 학습(2025) %d달 / 검증(2026) %d달" % (len(B), B.d.min(), B.d.max(), B.d.nunique(), LM, VM))
P("- 한 건 100만 기준 건당(비용·충격 뒤) 학습 %+.2f%% / 검증 %+.2f%% · 이긴 비율 %.0f%% / %.0f%%" % (B.r[B.L].mean(), B.r[~B.L].mean(), (B.r[B.L] > 0).mean() * 100, (B.r[~B.L] > 0).mean() * 100))
P("- 시가→종가 분포: 중앙 %+.1f%% · 상위 25%% %+.1f%% · 상위 10%% %+.1f%% · 상위 5%% %+.1f%% · 시가→종가와 전날 종가 대비의 상관 %.2f" % (B.oc.median(), B.oc.quantile(.75), B.oc.quantile(.9), B.oc.quantile(.95), B.oc.corr(B.dayr)))


def acct(z, Cap=3000e4, cap=500e4, k=0.10, px="g_vw"):
    z = z.sort_values(["d", "AH50"])
    amt = np.full(len(z), cap, float)
    if k: amt = np.minimum(amt, k * z.v41.values)
    amt = np.where(amt >= 30e4, amt, 0)
    cum = pd.Series(amt, index=z.index).groupby(z.d.values).cumsum().values
    amt = np.clip(Cap - (cum - amt), 0, amt)
    ok = amt >= 30e4; z = z[ok]; amt = amt[ok]
    r = z[px].values - impact(amt, z.a10.values) - impact(amt, z.v0f.values)
    pnl = pd.Series(r / 100 * amt / 1e4, index=z.index)
    pm = pnl.groupby(z.m.values).sum(); dp = pnl.groupby(z.d.values).sum()
    return dict(L=pnl[z.d < "20260101"].sum() / LM, V=pnl[z.d >= "20260101"].sum() / VM, tot=pnl.sum(), pm=(pm > 0).sum(), nm=len(pm), worst=dp.min() if len(dp) else 0, n=len(z), pnl=pnl, used=amt.sum() / 1e4 / z.d.nunique() if len(z) else 0)


rng = np.random.default_rng(7)
def ci_diff(a, b):
    """빠진 건 건당 - 남은 건 건당, 달 묶음 부트스트랩 95%"""
    ms = sorted(set(a.m) | set(b.m)); out = []
    ga = a.groupby("m").r.agg(["sum", "count"]).reindex(ms).fillna(0).values; gb = b.groupby("m").r.agg(["sum", "count"]).reindex(ms).fillna(0).values
    for _ in range(2000):
        k = rng.integers(0, len(ms), len(ms)); sa = ga[k].sum(0); sb = gb[k].sum(0)
        if sa[1] and sb[1]: out.append(sa[0] / sa[1] - sb[0] / sb[1])
    return np.percentile(out, 2.5), np.percentile(out, 97.5)


cells = 0
P("\n## 1) 낮 시가→종가 구간별 (한 건 100만 기준)\n")
P("| 시가→종가 | 건 학/검 | 건당 학습 | 건당 검증 | 이긴 비율 학/검 | 다음 날 시가까지 그냥 값(충격 전) 학/검 |"); P("|---|---|---|---|---|---|")
EDG = [-99, -5, -3, -1, 1, 3, 5, 7, 10, 15, 99]
for a, b in zip(EDG, EDG[1:]):
    g = B[(B.oc > a) & (B.oc <= b)]; l, v = g[g.L], g[~g.L]
    lab = "%+d%%↓" % b if a == -99 else "%+d%%↑" % a if b == 99 else "%+d ~ %+d%%" % (a, b)
    f = lambda s, c="r": "%+.2f%%" % s[c].mean() if len(s) else "-"
    P("| %s | %d / %d | %s | %s | %s / %s | %s / %s |" % (lab, len(l), len(v), f(l), f(v), "%.0f%%" % ((l.r > 0).mean() * 100) if len(l) else "-", "%.0f%%" % ((v.r > 0).mean() * 100) if len(v) else "-", f(l, "g_vw"), f(v, "g_vw")))

b0 = acct(B); h0 = acct(B, px="g_hi")
HDR = "| 빼는 기준 | 빠지는 건(비율) | 빠진 건 건당 학/검 | 남은 건 건당 학/검 | 빠진-남은 95% 구간 | 계좌 20달 합계(만) | 지금 대비 | 월 학/검(만) | 플러스 달 | 최악의 날(만) | 나아진 달/못한 달 | 최고가 매수 합계(지금 대비) |\n|---|---|---|---|---|---|---|---|---|---|---|---|"
def line(lab, m):
    global cells
    cells += 1
    x, k = B[m], B[~m]; a = acct(k); h = acct(k, px="g_hi")
    lo, hi = ci_diff(x, k) if len(x) > 10 else (np.nan, np.nan)
    pa = a["pnl"].groupby(k.loc[a["pnl"].index, "m"]).sum(); pb = b0["pnl"].groupby(B.loc[b0["pnl"].index, "m"]).sum()
    d = (pa.reindex(pb.index).fillna(0) - pb)
    f = lambda s: "%+.2f" % s.r.mean() if len(s) else "-"
    P("| %s | %d (%.0f%%) | %s / %s | %s / %s | %+.2f~%+.2f | %+.0f | %+.0f | %+.0f / %+.0f | %d/%d | %+.0f | %d / %d | %+.0f (%+.0f) |" % (
        lab, len(x), len(x) / len(B) * 100, f(x[x.L]), f(x[~x.L]), f(k[k.L]), f(k[~k.L]), lo, hi, a["tot"], a["tot"] - b0["tot"], a["L"], a["V"], a["pm"], a["nm"], a["worst"], (d > 0.5).sum(), (d < -0.5).sum(), h["tot"], h["tot"] - h0["tot"]))

P("\n## 2) 말한 그대로 — 시가→종가가 문턱보다 크면 뺌 (계좌 3천만 · 깊은 순)\n"); P(HDR)
P("| 안 뺌(지금) | 0 | - | %+.2f / %+.2f | - | %+.0f | 0 | %+.0f / %+.0f | %d/%d | %+.0f | - | %+.0f |" % (B.r[B.L].mean(), B.r[~B.L].mean(), b0["tot"], b0["L"], b0["V"], b0["pm"], b0["nm"], b0["worst"], h0["tot"]))
for th in (3, 5, 7, 10, 15, 20):
    line("시가→종가 > +%d%%" % th, B.oc > th)
P("\n## 3) 변형 — 전날 종가 대비(낮 등락)가 문턱보다 크면 뺌\n"); P(HDR)
for th in (5, 10, 15, 20):
    line("전날 종가 대비 > +%d%%" % th, B.dayr > th)
P("\n## 4) 변형 — 거꾸로(낮에 시가 대비 많이 빠진 건 빼기) · 둘 다\n"); P(HDR)
for th in (-3, -5, -7):
    line("시가→종가 < %d%%" % th, B.oc < th)
line("시가→종가 > +10% 이고 전날 종가 대비 > +10%", (B.oc > 10) & (B.dayr > 10))
P("\n- 하루 평균 쓰는 돈(지금): %.0f만 · 계좌 손익은 깊은 순으로 3천만까지라, 뺀 자리는 다음 종목이 채운다" % b0["used"])
P("\n시험 칸 %d" % cells)
(ROOT / "reports" / "nxt_oc_1125.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
if "--nolog" not in sys.argv:
    try:
        from verdict import log_trials
        log_trials("nxt_oc_1125", cells)
    except Exception as ex: print("칸 수 기록 실패:", repr(ex)[:200])
