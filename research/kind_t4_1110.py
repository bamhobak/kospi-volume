# -*- coding: utf-8 -*-
"""[미장 폭락 과잉 갭](T4)에 갭 구간 공시 빼기가 듣나 (2026-11-10 사용자 "이것도 살펴봐" · H0395 를 T4 로).
T4 = 나스닥 전날 -2.5%↓ 날 · 유니버스 거래대금 아래 1/2 · 갭 -2%↓ · 덜 반영(갭 − 짝 미장 예상 갭) 하위 10% → 시가 매수·종가 매도(research/t1_uni2_1021.py 정의).
    python research/kind_t4_1110.py
"""
import os, sys, sqlite3, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT), str(ROOT / "factory"), str(BASE)]
sys.stdout.reconfigure(encoding="utf-8")
import FinanceDataReader as fdr
import lab
H = lab.hist()[["date", "ticker", "oc", "gap", "rgap", "q_vm", "liq", "q_tr_res"]].dropna(subset=["oc", "gap", "liq"]).copy()
H = H[H.date >= "20160101"]; H["oc"] = H.oc - 0.23
X = fdr.DataReader("IXIC", "2015-01-01"); X = X[X.Close > 0]
us = X.Close.pct_change() * 100; us.index = us.index.strftime("%Y%m%d"); ud = us.index.values
H["us"] = H.date.map({d: (us.iloc[np.searchsorted(ud, d) - 1] if np.searchsorted(ud, d) > 0 else np.nan) for d in H.date.unique()})
T = H[(H.us <= -2.5) & (H.gap <= -2.0) & (H.q_tr_res <= 0.10) & (H.liq <= 0.5) & (H.gap > -27.5)].copy()
T["t1"] = (T.q_vm.fillna(1) <= 0.30) & (T.rgap <= -1.5) & (T.liq <= 2 / 3)
cal = np.array(sorted(H.date.unique())); cs = set(cal)
c = sqlite3.connect(BASE / "data" / "dart" / "kind_time.db")
E = pd.read_sql("select day, hm, kcode, title from kind where market in ('유가증권','코스닥')", c)
hm = E.hm.astype(int); trd = E.day.isin(cs)
nxt = cal[np.minimum(np.searchsorted(cal, E.day.values, side="right"), len(cal) - 1)]
E["gd"] = np.where(trd & (hm < 850), E.day, np.where(trd & (hm <= 1530), "", nxt))
S = set(zip(E.kcode, E.gd))
T["disc"] = [(t[:5], d) in S for t, d in zip(T.ticker.values, T.date.values)]
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def cell(z):
    if len(z) < 8: return "%d건" % len(z)
    d = z.groupby("date").oc.mean(); t = d.mean() / d.std() * np.sqrt(len(d)) if len(d) > 3 and d.std() > 0 else float("nan")
    return "%d건 **%+.2f** (중앙 %+.2f·승 %.0f%%) · 날 %d개 %+.2f t%.1f" % (len(z), z.oc.mean(), z.oc.median(), (z.oc > 0).mean() * 100, len(d), d.mean(), t)


P("# [미장 폭락 과잉 갭] × 갭 구간 공시 · 2026-11-10"); P("")
P("- 거래 %d건 · 신호 날 %d · 공시 있음 %.1f%% · 패널 끝 %s" % (len(T), T.date.nunique(), T.disc.mean() * 100, H.date.max())); P("")
P("| 무리 | 학습 16~22 | 검증 23~ |"); P("|---|---|---|")
ALL = T.disc | ~T.disc
for nm, m in (("전체", ALL), ("공시 없음", ~T.disc), ("공시 있음", T.disc), ("[갭 하락 조용주]와 안 겹침 · 공시 없음", ~T.t1 & ~T.disc), ("[갭 하락 조용주]와 안 겹침 · 공시 있음", ~T.t1 & T.disc)):
    P("| %s | %s | %s |" % (nm, cell(T[m & (T.date <= "20221231")]), cell(T[m & (T.date >= "20230101")])))
(ROOT / "reports" / "kind_t4_1110.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
from verdict import log_trials
log_trials("kind_t4_1110", 5)
