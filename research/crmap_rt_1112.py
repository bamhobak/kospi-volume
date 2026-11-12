# -*- coding: utf-8 -*-
"""H0411 검토관(redteam) — 반대매매 지도 데이 판: F≥1 & D+2 시가 갭 ≤ -1% → 시가→종가."""
import os, sys, json, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT / "factory"), str(ROOT), str(BASE)]
sys.stdout.reconfigure(encoding="utf-8")
import common as C
import redteam as RT
OUTD = Path("C:/temp/kp/crmap")
cal = pd.read_pickle(OUTD / "cal.pkl").values; tk = pd.read_pickle(OUTD / "tk.pkl").values
Z = np.load(OUTD / "fr.npz"); R1 = Z["h1"]; ok = Z["ok"]
Px = pd.read_pickle(C.CACHE / "factory_px.pkl")[["ticker", "date", "open", "close"]]
Px = Px[(Px.date >= "20090101") & Px.ticker.isin(set(tk))]
OP = Px.pivot(index="date", columns="ticker", values="open").reindex(index=cal, columns=tk).values
CL = Px.pivot(index="date", columns="ticker", values="close").reindex(index=cal, columns=tk).values
G = np.full_like(OP, np.nan); G[1:] = (OP[1:] / CL[:-1] - 1) * 100
okp = np.zeros_like(ok); okp[1:] = ok[:-1]
mkt = pd.Series(np.nanmean(np.where(okp & np.isfinite(R1), R1, np.nan), axis=1), index=cal)       # 그날 거래 가능 전 종목 시가→종가(비용 뒤)
E = pd.read_pickle(OUTD / "ev.pkl")
E = E[E["var"] == "지도 k1.4 m0.4 L3"].copy()
E["g"] = G[E.e.values, E.t.values]; E["edate"] = cal[E.e.values]
E = E.dropna(subset=["g", "r1"])
mk = lambda z: pd.DataFrame({"date": z.edate.values, "ticker": z.ticker.values, "ret": z.r1.values, "amt20": z.amt20.values / 1e8, "gap": z.g.values})
T = mk(E[(E.F >= 1) & (E.g <= -1)])
twin = mk(E[(E.F < 0.05) & (E.g <= -1)])
out = {}
for tag, sel in (("sel_none", None), ("sel_all", ("20100101", "20261110"))):
    R = RT.review("H0411_crmap_%s" % tag, T, mkt=mkt, twin=twin, sel=sel, mode="oc", conds=None, hold=1, ai=False, note="반대매매 지도 F≥1 & 시가 갭 -1%↓ 데이")
    out[tag] = R
    print("##", tag, "판정:", R.get("verdict"))
    for c in R["checks"]: print("  -", c["level"], c["name"], "|", c["note"])
