# -*- coding: utf-8 -*-
"""H0414 후속 — [장후 낙폭] T6 그림자 거래 안에서 장후 거래량 터짐(z≥2, Walkup 2009) 나누기."""
import os, sys, pickle, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT), str(ROOT / "factory"), str(BASE)]
sys.stdout.reconfigure(encoding="utf-8")
from verdict import log_trials
X = pd.read_pickle("C:/temp/kp/twin/ab.pkl")[["t", "d", "vz", "vall"]].rename(columns={"t": "ticker", "d": "date"})
T = pickle.load(open("C:/temp/kp/kind/t6.pkl", "rb"))["T"]
T = T.merge(X, on=["ticker", "date"], how="left")
T["live"] = T.AH50 <= -2.5
out = ["# [장후 낙폭] T6 × 장후 거래량 터짐 (H0414 후속) · 2026-11-12", "", "칸 = 건수 · 건당(19:51~20:00 VWAP 매수 → 다음 날 시가, 비용 0.23 뒤) · 날 바구니 · t", "",
       "| 무리 | 거래량 | 2025 | 2026 |", "|---|---|---|---|"]


def cell(z):
    if len(z) < 8: return "%d건" % len(z)
    d = z.groupby("date").r.mean(); t = d.mean() / d.std() * np.sqrt(len(d)) if len(d) > 3 and d.std() > 0 else float("nan")
    return "%d건 %+.2f · 날 %d **%+.2f** t%.1f" % (len(z), z.r.mean(), len(d), d.mean(), t)


n = 0
for nm, base in (("그림자 조건 전체", T), ("실주문 조건(장후 -2.5%↓)", T[T.live])):
    for vn, m in (("평소 z<2", base.vz < 2), ("터짐 z≥2", base.vz >= 2), ("터짐 z≥3", base.vz >= 3), ("값 없음", base.vz.isna())):
        z = base[m]
        out.append("| %s | %s | %s | %s |" % (nm, vn, cell(z[z.date < "20260101"]), cell(z[z.date >= "20260101"]))); n += 2
print("\n".join(out))
(ROOT / "reports" / "twin_t6_1112.md").write_text("\n".join(out) + "\n", encoding="utf-8")
log_trials("twin_t6_1112", n)
