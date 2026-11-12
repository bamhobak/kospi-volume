# -*- coding: utf-8 -*-
"""H0415 후속 — 격자 상위 후보 굳히기: 해마다 손익 · 좋은 날 몫 · 2020-03 빼고 · 하루 상한 바꾸기 · 검토관.
    python research/crmap5_1112.py → research/reports/crmap5_1112.md
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT / "factory"), str(ROOT), str(BASE)]
sys.stdout.reconfigure(encoding="utf-8")
import common as C
import redteam as RT
from verdict import log_trials
OUTD = Path("C:/temp/kp/crmap")
COST = 0.23
cal = pd.read_pickle(OUTD / "cal.pkl").values; tk = pd.read_pickle(OUTD / "tk.pkl").values; nd = len(cal)
Px = pd.read_pickle(C.CACHE / "factory_px.pkl")[["ticker", "date", "open", "close"]]
Px = Px[(Px.date >= "20090101") & Px.ticker.isin(set(tk))]
OP = Px.pivot(index="date", columns="ticker", values="open").reindex(index=cal, columns=tk).values
CL = Px.pivot(index="date", columns="ticker", values="close").reindex(index=cal, columns=tk).values
del Px
E0 = pd.read_pickle(OUTD / "ev.pkl")
E0 = E0[E0["var"].str.startswith("지도") & (E0.F >= 0.3)][["var", "d", "t", "F", "amt20"]]
E0 = E0[cal[E0.d.values] >= "20151201"]
HOLD = {"oc": 0, "o3": 2, "o5": 4}
okp = np.zeros(CL.shape, bool); okp[1:] = np.isfinite(CL[:-1]) & (CL[:-1] >= 1000)
R1 = (CL / OP - 1) * 100 - COST
mkt = pd.Series(np.nanmean(np.where(okp & (np.abs(R1) < 30), R1, np.nan), axis=1), index=cal)


def trades(var, F, gth, ex, size, daycap=5e7, off=2):
    E = E0[(E0["var"] == var) & (E0.F >= F)].copy()
    e = E.d.values + off; ok = e + 5 < nd; E = E[ok]; e = e[ok]; t = E.t.values
    E["e"] = e; E["date"] = cal[e]; E["ticker"] = tk[t]
    E["g"] = (OP[e, t] / CL[e - 1, t] - 1) * 100
    o = OP[e, t]; h = HOLD[ex]
    E["r"] = (CL[e + h, t] / o - 1) * 100 - COST
    E = E[np.isfinite(E.g) & (E.g > -29.5) & (E.g <= gth) & np.isfinite(E.r) & (E.r.abs() < 60)]
    E = E.sort_values(["date", "F"], ascending=[True, False]).drop_duplicates(["date", "t"])
    amt = np.full(len(E), size) if size > 1 else np.minimum(size * E.amt20.values, 1000e4)
    cum = pd.Series(amt).groupby(E.date.values).cumsum().values
    amt = np.where(cum <= daycap, amt, 0)
    p = amt / E.amt20.values * 100
    imp = np.maximum(0, 0.143 + 1.321 * np.sqrt(p)); fill = 1 / (1 + 3 * p)
    E["inv"] = amt * fill; E["pnl"] = E.inv * (E.r - imp) / 100; E["net"] = E.r - imp
    return E[E.inv > 0]


CANDS = [("지금 판", "지도 k1.4 m0.4 L3", 1.0, -1, "oc", 200e4),
         ("A 갭-3·3일", "지도 k1.4 m0.4 L3", 0.3, -3, "o3", 200e4),
         ("B 갭-3·5일", "지도 k1.4 m0.4 L3", 0.3, -3, "o5", 200e4),
         ("C 갭-2·3일", "지도 k1.4 m0.4 L3", 0.3, -2, "o3", 200e4),
         ("D k1.3 갭-3·3일", "지도 k1.3 m0.4 L3", 0.3, -3, "o3", 200e4),
         ("E F≥1 갭-2·5일", "지도 k1.4 m0.4 L3", 1.0, -2, "o5", 200e4),
         ("F 갭-3·3일·거래대금0.5%", "지도 k1.3 m0.4 L3", 0.3, -3, "o3", 0.005)]
OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True)); n = 0
P("# [반대매매] 격자 상위 후보 굳히기 (H0415 후속) · 2026-11-12"); P("")
P("D+2 시가(갭 문턱 이하일 때) 매수 · 하루 새 매수 상한 5천만(F 큰 순) · 체결 손해·체결률 뒤 · 연 손익 만원"); P("")
P("| 후보 | 산 것/년 | 건당(손해 뒤) | 연 손익 16~22 | 연 손익 23~ | 2020-03 빼면 16~22 | 손익 좋은 날 1위 몫 | 좋은 날 10개 몫 | 플러스 해 | 하루 상한 2천만이면 16~22/23~ |"); P("|---|---|---|---|---|---|---|---|---|---|")
YR = {}
for nm, var, F, g, ex, sz in CANDS:
    T = trades(var, F, g, ex, sz)
    a = T[T.date < "20230101"]; b = T[T.date >= "20230101"]
    ya, yb = a.pnl.sum() / 7 / 1e4, b.pnl.sum() / (len(cal[cal >= "20230101"]) / 250) / 1e4
    a2 = a[~a.date.str.startswith("202003")]
    dp = T.groupby("date").pnl.sum().sort_values(ascending=False)
    yp = T.groupby(T.date.str[:4]).pnl.sum() / 1e4; YR[nm] = yp
    T2 = trades(var, F, g, ex, sz, daycap=2e7)
    y2a, y2b = T2[T2.date < "20230101"].pnl.sum() / 7 / 1e4, T2[T2.date >= "20230101"].pnl.sum() / (len(cal[cal >= "20230101"]) / 250) / 1e4
    P("| %s | %.0f | %+.2f%% | %+.0f | %+.0f | %+.0f | %.0f%% | %.0f%% | %d/%d | %+.0f / %+.0f |" % (
        nm, len(T) / 10.85, (T.pnl.sum() / T.inv.sum() * 100), ya, yb, a2.pnl.sum() / 7 / 1e4, dp.iloc[0] / T.pnl.sum() * 100, dp.iloc[:10].sum() / T.pnl.sum() * 100,
        int((yp > 0).sum()), len(yp), y2a, y2b)); n += 6
P("")
P("## 해마다 손익(만원)"); P("")
yrs = sorted(set().union(*[set(v.index) for v in YR.values()]))
P("| 후보 | " + " | ".join(yrs) + " |"); P("|---|" + "---|" * len(yrs))
for nm, yp in YR.items(): P("| %s | %s |" % (nm, " | ".join(("%+.0f" % yp[y]) if y in yp.index else "-" for y in yrs)))
P("")
P("## 검토관(건당 수익 기준, 2016~)"); P("")
for nm, var, F, g, ex, sz in CANDS[1:3]:
    T = trades(var, F, g, ex, sz)
    tw = trades(var, F, 9, ex, sz)                                   # 뒤집은 짝: 갭 문턱 없음(얕게 열린 것까지)
    tw = tw[tw.g > -1]
    X = pd.DataFrame({"date": T.date.values, "ticker": T.ticker.values, "ret": T.r.values, "amt20": T.amt20.values / 1e8, "gap": T.g.values})
    TW = pd.DataFrame({"date": tw.date.values, "ticker": tw.ticker.values, "ret": tw.r.values})
    Rv = RT.review("H0415_" + nm.split()[0], X, mkt=mkt, twin=TW, sel=None, mode="oc", conds=None, hold=HOLD[ex] + 1, ai=False)
    P("- **%s** 판정 %s: " % (nm, Rv["verdict"]) + " · ".join("%s %s(%s)" % (c["level"], c["name"], c["note"][:70]) for c in Rv["checks"]))
P("")
(ROOT / "reports" / "crmap5_1112.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
log_trials("crmap5_1112", n)
