# -*- coding: utf-8 -*-
"""[반대매매] 200만·300만 다 살 수 있나 — 신호 종목의 시가 단일가(1분봉 첫 봉, 2022-12~) 거래대금과 '시가 = 지정가' 비율, 매도 날 종가 단일가 거래대금."""
import os, sys, glob, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT / "factory"), str(ROOT), str(BASE)]
sys.stdout.reconfigure(encoding="utf-8")
import common as C
OUTD = Path("C:/temp/kp/crmap")
cal = pd.read_pickle(OUTD / "cal.pkl").values; tk = pd.read_pickle(OUTD / "tk.pkl").values; nd = len(cal)
Px = pd.read_pickle(C.CACHE / "factory_px.pkl")[["ticker", "date", "open", "close"]]
Px = Px[(Px.date >= "20221101") & Px.ticker.isin(set(tk))]
OP = Px.pivot(index="date", columns="ticker", values="open").reindex(index=cal, columns=tk).values
CL = Px.pivot(index="date", columns="ticker", values="close").reindex(index=cal, columns=tk).values
E = pd.read_pickle(OUTD / "ev.pkl")
E = E[(E["var"] == "지도 k1.4 m0.4 L3") & (E.F >= 0.3)][["d", "t", "F", "amt20"]]
E = E[cal[E.d.values] >= "20221201"].copy()
e = E.d.values + 2; ok = e + 7 < nd; E = E[ok]; e = e[ok]; t = E.t.values
E["e"] = e; E["date"] = cal[e]; E["ticker"] = tk[t]
E["pc"] = CL[e - 1, t]; E["op"] = OP[e, t]; E["g"] = (E.op / E.pc - 1) * 100
E = E[np.isfinite(E.g) & (E.g <= -2) & (E.g > -29.5)].drop_duplicates(["date", "ticker"])


def tick(p):
    for lim, s in ((2000, 1), (5000, 5), (20000, 10), (50000, 50), (200000, 100), (500000, 500)):
        if p < lim: return s
    return 1000


E["lim2"] = [int(np.floor(pc * 0.98 / tick(pc * 0.98)) * tick(pc * 0.98)) for pc in E.pc]
E["lim3"] = [int(np.floor(pc * 0.97 / tick(pc * 0.97)) * tick(pc * 0.97)) for pc in E.pc]
E["sell3"] = cal[E.e.values + 2]; E["sell7"] = cal[E.e.values + 6]
rows = []
need = E.groupby("ticker")
for tkr, g in need:
    f = BASE / "data" / "m1" / "KR" / "bf" / ("%s.parquet" % tkr)
    if not f.exists(): continue
    B = pd.read_parquet(f, columns=["ts", "o", "c", "v"])
    k = pd.to_datetime(B.ts.values + 9 * 3600, unit="s")
    B["d"] = k.strftime("%Y%m%d"); B["hm"] = k.hour * 100 + k.minute
    B = B[B.v > 0]
    first = B[(B.hm >= 901) & (B.hm <= 1530)].sort_values("ts").groupby("d").first()
    last = B[(B.hm >= 1521) & (B.hm <= 1531)].sort_values("ts").groupby("d").last()
    for r in g.itertuples():
        if r.date not in first.index: continue
        fo = first.loc[r.date]
        rows.append(dict(ticker=tkr, date=r.date, g=r.g, op_m1=float(fo.o), auc=float(fo.o * fo.v), amt20=r.amt20, lim2=r.lim2, lim3=r.lim3,
                         cl3=float(last.loc[r.sell3].c * last.loc[r.sell3].v) if r.sell3 in last.index else np.nan,
                         cl7=float(last.loc[r.sell7].c * last.loc[r.sell7].v) if r.sell7 in last.index else np.nan))
R = pd.DataFrame(rows)
print("신호(갭 -2%%↓, 2022-12~) %d건 중 1분봉 있음 %d건" % (len(E), len(R)))
q = lambda s: "중앙 %.0f만 · 하위 25%% %.0f만 · 하위 10%% %.0f만" % (s.median() / 1e4, s.quantile(0.25) / 1e4, s.quantile(0.10) / 1e4)
print("시가 단일가(첫 봉) 거래대금:", q(R.auc))
print("매도 날 종가 단일가(마지막 봉) 거래대금 3일째:", q(R.cl3.dropna()), "· 7일째:", q(R.cl7.dropna()))
for amt in (200e4, 300e4, 500e4):
    sh = amt / R.auc
    print("%d만 = 시가 단일가 거래대금의 중앙 %.1f%% · 10%% 넘는 건 %.0f%% · 30%% 넘는 건 %.0f%%" % (amt / 1e4, sh.median() * 100, (sh > 0.1).mean() * 100, (sh > 0.3).mean() * 100))
print("시가 = 지정가(일부 체결 위험) 비율: 갭 -2%%판 %.1f%% · 갭 -3%%판(-3%%↓ 신호 중) %.1f%%" % ((R.op_m1 == R.lim2).mean() * 100,
      (R[R.g <= -3].op_m1 == R[R.g <= -3].lim3).mean() * 100))
print("시가가 지정가보다 한 호가 이내 위·아래(경계 근처) %.1f%%" % ((np.abs(R.op_m1 - R.lim2) <= [tick(x) for x in R.lim2]).mean() * 100))
