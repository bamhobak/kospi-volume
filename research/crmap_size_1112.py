# -*- coding: utf-8 -*-
"""T8 [반대매매] 크기 — 월 건수·종목당 금액별 연 손익·필요 자금 (실전 규칙 그대로: k1.4 m0.4 L3 · F≥1 · 시가 갭 ≤-1% · 하루 최대 10종목 F 큰 순).
체결 손해 = 0.143 + 1.321√p (p = 금액 ÷ 20일 거래대금 %) · 체결률 = 1/(1+3p) — redteam·fshadow 와 같은 모형. 비용 0.23 은 r1 에 이미 빠짐.
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT), str(ROOT / "factory"), str(BASE)]
sys.stdout.reconfigure(encoding="utf-8")
import common as C
OUTD = Path("C:/temp/kp/crmap")
cal = pd.read_pickle(OUTD / "cal.pkl").values; tk = pd.read_pickle(OUTD / "tk.pkl").values
Px = pd.read_pickle(C.CACHE / "factory_px.pkl")[["ticker", "date", "open", "close"]]
Px = Px[(Px.date >= "20090101") & Px.ticker.isin(set(tk))]
OP = Px.pivot(index="date", columns="ticker", values="open").reindex(index=cal, columns=tk).values
CL = Px.pivot(index="date", columns="ticker", values="close").reindex(index=cal, columns=tk).values
G = np.full_like(OP, np.nan); G[1:] = (OP[1:] / CL[:-1] - 1) * 100
E = pd.read_pickle(OUTD / "ev.pkl")
E = E[E["var"] == "지도 k1.4 m0.4 L3"].copy()
E["g"] = G[E.e.values, E.t.values]; E["edate"] = cal[E.e.values]
E = E[(E.F >= 1) & (E.g <= -1) & (E.g > -29) & E.r1.notna()].copy()
E = E.sort_values(["edate", "F"], ascending=[True, False]); E["k"] = E.groupby("edate").cumcount(); E = E[E.k < 10]
E = E[E.edate >= "20160101"]
yrs = {"16~22": E[E.edate < "20230101"].edate.str[:4].nunique(), "23~": (len(cal[cal >= "20230101"]) / 250)}
print("거래", len(E), "· 날", E.edate.nunique(), "· 2016~ 월평균 %.1f건 · 거래 있는 달 비율 %.0f%%" % (len(E) / (len(cal[cal >= "20160101"]) / 21), E.edate.str[:6].nunique() / len(set(c[:6] for c in cal if c >= "20160101")) * 100))
for per, z in (("16~22", E[E.edate < "20230101"]), ("23~", E[E.edate >= "20230101"])):
    m = z.groupby(z.edate.str[:6]).size()
    print(per, "월 평균 %.1f건 · 중앙 %d · 많은 달 %d" % (len(z) / (yrs[per] * 12), m.median(), m.max()), "· 하루 건수 평균 %.1f · 95%% %d" % (z.groupby("edate").size().mean(), z.groupby("edate").size().quantile(0.95)))
print("20일 거래대금 중앙 %.0f억 · 하위 10%% %.0f억" % (E.amt20.median() / 1e8, E.amt20.quantile(0.1) / 1e8))
print()
print("| 종목당 | 건당 순수익(손해 뒤) | 연 손익 16~22 | 연 손익 23~ | 하루 최대 투입(95%) | 하루 최대 투입(최대) | 연 손익 ÷ 95% 투입 |")
print("|---|---|---|---|---|---|---|")
for amt in (50e4, 100e4, 200e4, 300e4, 500e4, 1000e4, 2000e4):
    p = amt / E.amt20 * 100
    imp = np.maximum(0, 0.143 + 1.321 * np.sqrt(p)); fill = 1 / (1 + 3 * p)
    inv = amt * fill; pnl = inv * (E.r1 - imp) / 100
    E["pnl"] = pnl; E["inv"] = inv
    a = E[E.edate < "20230101"]; b = E[E.edate >= "20230101"]
    day = E.groupby("edate").inv.sum()
    yr_a = a.pnl.sum() / yrs["16~22"] / 1e4; yr_b = b.pnl.sum() / yrs["23~"] / 1e4
    net = float((inv * (E.r1 - imp)).sum() / inv.sum())
    print("| %d만 | %+.2f%% | %+.0f만 | %+.0f만 | %.0f만 | %.0f만 | %.0f%% |" % (amt / 1e4, net, yr_a, yr_b, day.quantile(0.95) / 1e4, day.max() / 1e4, (yr_a + yr_b) / 2 / (day.quantile(0.95) / 1e4) * 100))
