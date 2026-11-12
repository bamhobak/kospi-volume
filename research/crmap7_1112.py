# -*- coding: utf-8 -*-
"""H0415 후속 3 — 보유 기간 넓히기 (2026-11-12 사용자 "10일 15일도 실측해봤어?").
지도 k1.4 · F≥0.3 · D+2 시가 갭 ≤ -2 / -3 % → 보유 1·2·3·5·7·10·15·20 거래일째 종가. 금액 200만·하루 5천만 / 300만·하루 1억.
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT / "factory"), str(ROOT), str(BASE)]
sys.stdout.reconfigure(encoding="utf-8")
import common as C
from verdict import log_trials
OUTD = Path("C:/temp/kp/crmap"); COST = 0.23
cal = pd.read_pickle(OUTD / "cal.pkl").values; tk = pd.read_pickle(OUTD / "tk.pkl").values; nd = len(cal)
Px = pd.read_pickle(C.CACHE / "factory_px.pkl")[["ticker", "date", "open", "close"]]
Px = Px[(Px.date >= "20090101") & Px.ticker.isin(set(tk))]
OP = Px.pivot(index="date", columns="ticker", values="open").reindex(index=cal, columns=tk).values
CL = Px.pivot(index="date", columns="ticker", values="close").reindex(index=cal, columns=tk).values
del Px
E0 = pd.read_pickle(OUTD / "ev.pkl")
E0 = E0[(E0["var"] == "지도 k1.4 m0.4 L3") & (E0.F >= 0.3)][["d", "t", "F", "amt20"]]
E0 = E0[cal[E0.d.values] >= "20151201"].copy()
e = E0.d.values + 2; ok = e + 21 < nd; E0 = E0[ok]; e = e[ok]; t = E0.t.values
E0["e"] = e; E0["date"] = cal[e]; E0["g"] = (OP[e, t] / CL[e - 1, t] - 1) * 100
o = OP[e, t]
HS = (1, 2, 3, 5, 7, 10, 15, 20)
for h in HS:
    r = (CL[e + h - 1, t] / o - 1) * 100 - COST
    r[(np.abs(r) > 80) | ~np.isfinite(r)] = np.nan
    E0["r%d" % h] = r
YB = len(cal[cal >= "20230101"]) / 250
imp = lambda p: np.maximum(0, 0.143 + 1.321 * np.sqrt(p)); fill = lambda p: 1 / (1 + 3 * p)
OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True)); n = 0
P("# [반대매매] 보유 기간 넓히기 1~20일 (H0415 후속 3) · 2026-11-12"); P("")
P("지도 k1.4 · F≥0.3 · D+2 시가 갭 문턱 이하 매수 → 보유 h 거래일째(매수일 = 1일째) 종가 · 체결 손해·체결률 뒤 · 필요 자금 = 들고 있는 돈 95%(최대)"); P("")
for gth in (-2, -3):
    E = E0[(E0.g > -29.5) & (E0.g <= gth)].sort_values(["date", "F"], ascending=[True, False]).drop_duplicates(["date", "t"]).reset_index(drop=True)
    for amt, dc in ((200e4, 5e7), (300e4, 1e8)):
        P("## 갭 ≤%d%% · 종목당 %d만 · 하루 새 매수 상한 %d천만" % (gth, amt / 1e4, dc / 1e7)); P("")
        P("| 보유 | 건당(손해 전) | 날 바구니 t | 건당(손해 뒤) | 연 손익 16~22 | 연 손익 23~ | 2023~25 평균 | 플러스 해 | 최악의 해 | 필요 자금 95% (최대) | 연 손익(평균)÷자금 |"); P("|---|---|---|---|---|---|---|---|---|---|---|")
        for h in HS:
            z = E.dropna(subset=["r%d" % h])
            a = np.full(len(z), amt); cum = pd.Series(a).groupby(z.date.values).cumsum().values; a = np.where(cum <= dc, a, 0)
            p = a / z.amt20.values * 100; inv = a * fill(p); pnl = inv * (z["r%d" % h].values - imp(p)) / 100
            pnl = np.nan_to_num(pnl); inv = np.nan_to_num(inv)
            tr = z.date.values < "20230101"
            ya, yb = pnl[tr].sum() / 7 / 1e4, pnl[~tr].sum() / YB / 1e4
            yrs = pd.Series(pnl).groupby(z.date.str[:4].values).sum() / 1e4
            yrs = yrs[yrs.index >= "2016"]
            cd = pd.Series(inv, index=z.e.values).groupby(level=0).sum()
            cd = cd.reindex(range(cd.index.min(), cd.index.max() + h + 1), fill_value=0).rolling(h, min_periods=1).sum()
            cd = cd[cd > 0]
            dd = z.groupby("date")["r%d" % h].mean(); tt = dd.mean() / dd.std() * np.sqrt(len(dd))
            need = cd.quantile(0.95) / 1e4
            P("| %d일 | %+.2f%% | %.1f | %+.2f%% | %+.0f만 | %+.0f만 | %+.0f만 | %d/%d | %+.0f만 | %.0f만 (%.0f만) | %.0f%% |" % (
                h, z["r%d" % h].mean(), tt, pnl.sum() / max(inv.sum(), 1) * 100, ya, yb, yrs.reindex(["2023", "2024", "2025"]).mean(), (yrs > 0).sum(), len(yrs), yrs.min(),
                need, cd.max() / 1e4, (ya * 7 + yb * YB) / (7 + YB) / max(need, 1) * 100)); n += 1
        P("")
(ROOT / "reports" / "crmap7_1112.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
log_trials("crmap7_1112", n)
