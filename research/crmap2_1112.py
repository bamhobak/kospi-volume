# -*- coding: utf-8 -*-
"""H0411 후속 — 지도 모델 꼭대기 칸(강제 물량 ÷ 거래대금 F 큰 것)만 파기: 옛날 구간·해마다·T1 겹침·시가 갭·F 문턱.
    python research/crmap2_1112.py   → research/reports/crmap2_1112.md
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT), str(ROOT / "factory"), str(BASE)]
sys.stdout.reconfigure(encoding="utf-8")
import lab, common as C
from verdict import log_trials
OUTD = Path("C:/temp/kp/crmap")
E = pd.read_pickle(OUTD / "ev.pkl")
E = E[E["var"].str.startswith("지도")].copy()
cal = pd.read_pickle(OUTD / "cal.pkl").values
E["edate"] = cal[E.e.values]
Px = pd.read_pickle(C.CACHE / "factory_px.pkl")[["ticker", "date", "open", "close"]]
Px = Px[Px.date >= "20090101"].sort_values(["ticker", "date"])
Px["pc"] = Px.groupby("ticker").close.shift(1)
Px["egap"] = (Px.open / Px.pc - 1) * 100
E = E.merge(Px[["ticker", "date", "egap"]].rename(columns={"date": "edate"}), on=["ticker", "edate"], how="left")
H = lab.hist()[["ticker", "date", "gap", "rgap", "q_vm", "liq"]].copy()
H["gq"] = H.groupby("date").gap.rank(pct=True)
H["t1"] = (H.q_vm.fillna(1) <= 0.30) & (H.liq <= 2 / 3) & (H.gq <= 0.40) & (H.rgap <= -1.5) & (H.gap > -27.5)
E = E.merge(H[["ticker", "date", "t1", "rgap"]].rename(columns={"date": "edate"}), on=["ticker", "edate"], how="left")
E["t1"] = E.t1.fillna(False)
PER = (("옛날 10~15", "20100101", "20151231"), ("학습 16~22", "20160101", "20221231"), ("검증 23~", "20230101", "20991231"))
OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))


def cell(z, col):
    z = z.dropna(subset=[col])
    if len(z) < 10: return "%d건" % len(z)
    dd = z.groupby("date")[col].mean()
    t = dd.mean() / dd.std() * np.sqrt(len(dd)) if len(dd) > 3 and dd.std() > 0 else float("nan")
    return "%d건 %+.2f · 날 %d **%+.2f** t%.1f" % (len(z), z[col].mean(), len(dd), dd.mean(), t)


per = lambda z, a, b: z[(z.date >= a) & (z.date <= b)]
P("# 반대매매 지도 꼭대기 칸 파기 (H0411 후속) · 2026-11-12"); P("")
P("D+2 시가 매수 · 칸 = 건수 건당 · 날 바구니 **평균** t (비용 0.23 뒤)"); P("")
n = 0
for v in ("지도 k1.4 m0.5 L3", "지도 k1.4 m0.4 L3", "지도 k1.3 m0.4 L3"):
    z0 = E[E["var"] == v]
    P("## %s" % v); P("")
    P("| 무리 | 보유 | " + " | ".join(p for p, _, _ in PER) + " |"); P("|---|---|---|---|---|")
    for nm, m in (("F≥0.5", z0.F >= 0.5), ("F≥1", z0.F >= 1), ("F≥2", z0.F >= 2),
                  ("F≥1 · T1 아님", (z0.F >= 1) & ~z0.t1), ("F≥1 · T1 겹침", (z0.F >= 1) & z0.t1),
                  ("F≥1 · 매수 날 갭 -2%↓", (z0.F >= 1) & (z0.egap <= -2)), ("F≥1 · 매수 날 갭 -2% 위", (z0.F >= 1) & (z0.egap > -2))):
        z = z0[m]
        for h in (1, 5):
            P("| %s | %s | %s |" % (nm, "당일" if h == 1 else "5일", " | ".join(cell(per(z, a, b), "r%d" % h) for _, a, b in PER))); n += 3
    P("")
    z = z0[z0.F >= 1]
    y = z.groupby(z.date.str[:4]).agg(n=("r1", "size"), days=("date", "nunique"))
    dd1 = z.groupby(["date"]).r1.mean(); dd5 = z.groupby(["date"]).r5.mean()
    y["day1"] = dd1.groupby(dd1.index.str[:4]).mean(); y["day5"] = dd5.groupby(dd5.index.str[:4]).mean()
    P("F≥1 해마다(날 바구니 당일/5일): " + " · ".join("%s %d건 %+.2f/%+.2f" % (k, r.n, r.day1, r.day5) for k, r in y.iterrows()))
    P("F≥1 T1 겹침 비율 %.1f%% · 하루 평균 %.1f건 · 최악의 날 당일 %.1f%%" % (z.t1.mean() * 100, len(z) / max(z.date.nunique(), 1), dd1.min()))
    P("")
(ROOT / "reports" / "crmap2_1112.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
log_trials("crmap2_1112", n)
