# -*- coding: utf-8 -*-
"""H0411 후속 2 — '강제 물량 큼(F) & D+2 시가가 실제로 빠져 열림'이 그냥 갭 하락 되돌림인지 가르기.
대조 = 같은 매수 날 · 시가 갭이 같은 칸(±1%p) · 지도 사건 아님 종목의 시가→종가. 갭 문턱·F 문턱·매수 날 시장 갭 변형.
    python research/crmap3_1112.py → research/reports/crmap3_1112.md
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT), str(ROOT / "factory"), str(BASE)]
sys.stdout.reconfigure(encoding="utf-8")
import common as C
from verdict import log_trials
OUTD = Path("C:/temp/kp/crmap")
cal = pd.read_pickle(OUTD / "cal.pkl").values; tk = pd.read_pickle(OUTD / "tk.pkl").values
Z = np.load(OUTD / "fr.npz"); R1 = Z["h1"]; R5 = Z["h5"]; ok = Z["ok"]
Px = pd.read_pickle(C.CACHE / "factory_px.pkl")[["ticker", "date", "open", "close"]]
Px = Px[(Px.date >= "20090101") & Px.ticker.isin(set(tk))]
OP = Px.pivot(index="date", columns="ticker", values="open").reindex(index=cal, columns=tk).values
CL = Px.pivot(index="date", columns="ticker", values="close").reindex(index=cal, columns=tk).values
G = np.full_like(OP, np.nan); G[1:] = (OP[1:] / CL[:-1] - 1) * 100
G[~np.isfinite(G) | (np.abs(G) > 30)] = np.nan
okp = np.zeros_like(ok); okp[1:] = ok[:-1]                    # 전날 기준 거래 가능(1,000원·거래대금·불연속)
MG = np.nanmedian(np.where(okp, G, np.nan), axis=1)            # 그날 시장 갭(중앙)
E = pd.read_pickle(OUTD / "ev.pkl")
E = E[E["var"].str.startswith("지도")].copy()
E["g"] = G[E.e.values, E.t.values]; E["mg"] = MG[E.e.values]
E["edate"] = cal[E.e.values]
evset = {}
for v, z in E.groupby("var"): evset[v] = set(zip(z.e.values, z.t.values))
PER = (("옛날 10~15", "20100101", "20151231"), ("학습 16~22", "20160101", "20221231"), ("검증 23~", "20230101", "20991231"))
OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))


def ctrl(z, v, col):
    """같은 매수 날 · 갭 ±1%p · 사건 아님 · 전날 거래 가능 종목 평균."""
    RR = R1 if col == "r1" else R5
    out = []
    S = evset[v]
    for e, g in z.groupby("e"):
        row = G[e]; pool = okp[e] & np.isfinite(row) & np.isfinite(RR[e])
        for t, x in zip(g.t.values, g.g.values):
            sel = pool & (np.abs(row - x) <= 1.0)
            sel[t] = False
            idx = np.nonzero(sel)[0]
            idx = [i for i in idx if (e, i) not in S]
            out.append(np.nanmean(RR[e][idx]) if len(idx) >= 3 else np.nan)
    return pd.Series(out, index=np.concatenate([g.index.values for _, g in z.groupby("e")]))


def cell(z, col):
    z = z.dropna(subset=[col])
    if len(z) < 10: return "%d건" % len(z)
    dd = z.groupby("edate")[col].mean()
    t = dd.mean() / dd.std() * np.sqrt(len(dd)) if len(dd) > 3 and dd.std() > 0 else float("nan")
    return "%d건 · 날 %d **%+.2f** t%.1f" % (len(z), len(dd), dd.mean(), t)


per = lambda z, a, b: z[(z.edate >= a) & (z.edate <= b)]
P("# 반대매매 지도 × 시가 갭 — 그냥 갭 되돌림인가 (H0411 후속 2) · 2026-11-12"); P("")
P("- 사건 = 지도 모델이 셈한 강제 물량 ÷ 20일 거래대금 F 이상 · D+2 매수 날 시가 갭 문턱 이하 → 시가 매수 · 칸 = 날 바구니 **평균** t (비용 0.23 뒤)")
P("- 대조 = 같은 매수 날 · 시가 갭 ±1%p · 지도 사건 아닌 종목의 같은 보유 평균 · '대조 대비' = 사건 − 대조"); P("")
n = 0
for v in ("지도 k1.4 m0.4 L3", "지도 k1.3 m0.4 L3", "지도 k1.4 m0.5 L3", "지도 k1.5 m0.4 L3"):
    z0 = E[E["var"] == v].dropna(subset=["g"])
    P("## %s" % v); P("")
    P("| F | 갭 | 보유 | " + " | ".join(p for p, _, _ in PER) + " |"); P("|---|---|---|---|---|---|")
    for F_ in (0.5, 1.0, 2.0):
        for gt in (-1.0, -2.0, -4.0):
            z = z0[(z0.F >= F_) & (z0.g <= gt)].copy()
            if len(z) < 20: continue
            for col in ("r1", "r5"):
                if F_ != 1.0 and col == "r5": continue
                z["c"] = ctrl(z, v, col); z["x"] = z[col] - z["c"]
                P("| %.1f | %+.0f%%↓ | %s | %s |" % (F_, gt, "당일" if col == "r1" else "5일", " | ".join(cell(per(z, a, b), col) for _, a, b in PER)))
                P("| | | ↳ 대조 대비 | %s |" % " | ".join(cell(per(z, a, b), "x") for _, a, b in PER)); n += 6
    # 시장 갭 국면
    z = z0[(z0.F >= 1) & (z0.g <= -2)].copy()
    P("")
    P("F≥1 · 갭 -2%↓ — 그날 시장 갭별 당일: " + " · ".join("%s %s" % (nm, cell(z[m], "r1")) for nm, m in (("시장 갭 -1%↓", z.mg <= -1), ("-1~0", (z.mg > -1) & (z.mg <= 0)), ("0↑", z.mg > 0))))
    yy = z.groupby("edate").r1.mean()
    P("F≥1 · 갭 -2%↓ 해마다(날 바구니 당일): " + " · ".join("%s %d날 %+.2f" % (k, len(g), g.mean()) for k, g in yy.groupby(yy.index.str[:4])))
    P("하루 평균 %.1f건 · 연 %.0f건 · 최악의 날 %.1f%% · 하위 5%% 날 %.1f%%" % (len(z) / max(z.edate.nunique(), 1), len(z) / 17.8, yy.min(), yy.quantile(0.05)))
    P("")
(ROOT / "reports" / "crmap3_1112.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
log_trials("crmap3_1112", n)
