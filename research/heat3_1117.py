# -*- coding: utf-8 -*-
"""H0425 단기과열 지정 — 굳히기 (2026-11-17). 판 D: 단일가 첫날(D+1) 마지막 단일가(종가)에 사서 셋째 날(D+3) 종가에 판다.
① 대조: 같은 날 · 지정 안 됨 · 5일 오름폭 닮은(±15%p, +15%↑) 종목의 같은 구간 ② 예고만 받고 지정 안 된 것 ③ 위험: 분위수·최악·연속 손실
④ 계좌: 건당 200만·50만, 하루 한도 없이 — 연도별 손익·가장 깊은 낙폭·동시에 든 최대 건수 ⑤ 거래대금별·시장별(D 판) ⑥ 이웃 판(문턱 흔들기)
"""
import math, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parent.parent; COST = 0.23
OUT = []; P_ = lambda s="": (OUT.append(s), print(s, flush=True))
t_ = lambda s: s.mean() / s.std(ddof=1) * math.sqrt(len(s)) if len(s) > 2 and s.std(ddof=1) > 0 else 0.0
P = pd.read_pickle(BASE / "research" / "cache" / "factory_px.pkl"); P = P[P.date >= "20151001"]
cal = sorted(P.date.unique()); ci = {d: i for i, d in enumerate(cal)}; tk = sorted(P.ticker.unique()); ti = {t: i for i, t in enumerate(tk)}
W = lambda col: P.pivot(index="date", columns="ticker", values=col).reindex(index=cal, columns=tk).values.astype(np.float64)
OP, HI, CL = W("open"), W("high"), W("close"); del P; nd, nt = CL.shape
sh = lambda A, k: np.vstack([A[k:], np.full((k, nt), np.nan)])
R5 = (CL / np.vstack([np.full((5, nt), np.nan), CL[:-5]]) - 1) * 100
RD = (sh(CL, 3) / sh(CL, 1) - 1) * 100 - COST; RD[(np.abs(RD) > 80) | ~np.isfinite(RD)] = np.nan
K = pd.read_pickle("C:/temp/kp/heat_ev.pkl")
EV = np.zeros((nd, nt), bool); EV[K.i.values, K.j.values] = True
EV3 = pd.DataFrame(EV).rolling(4, min_periods=1).max().values.astype(bool)          # 최근 지정(단일가 중)도 대조에서 뺌
K["rD"] = RD[K.i.values, K.j.values]; K = K[~K.lockc1].dropna(subset=["rD"]).copy()


def ctrl(i, r5):
    m = ~EV3[i] & (CL[i] >= 1000) & (R5[i] >= 15) & (np.abs(R5[i] - r5) <= 15)
    v = RD[i][m]; v = v[np.isfinite(v)]
    return (v.mean(), len(v)) if len(v) >= 2 else (np.nan, len(v))


cc = [ctrl(i, r) for i, r in zip(K.i.values, K.r5.values)]; K["cD"] = [x[0] for x in cc]; K["cn"] = [x[1] for x in cc]
PER = (("학습 16~22", "20160101", "20221231"), ("검증 23~", "20230101", "20991231"))
P_("# H0425 [단기과열 단일가] 굳히기 — 단일가 첫날 종가 매수 → 셋째 날 종가 매도\n")
P_("## 1. 대조(같은 날 · 지정 안 된 닮은 급등주 · 같은 구간)\n\n| 기간 | 건 | 규칙 건당 | 닮은 급등주 | 차이(날 바구니 t) | 대조 있는 건 |\n|---|---|---|---|---|---|")
for nm, a, b in PER:
    z = K[(K.day >= a) & (K.day <= b)]; e = z.dropna(subset=["cD"]); d = e.assign(x=e.rD - e.cD).groupby("day").x.mean()
    P_("| %s | %d | %+.2f%% | %+.2f%% | %+.2f (t%.1f) | %d |" % (nm, len(z), z.rD.mean(), e.cD.mean(), d.mean(), t_(d), len(e)))
P_("\n## 2. 위험\n\n| 기간 | 건 | 평균 | 중앙 | 승률 | 아래 5% | 아래 1% | 최악 | 위 5% | 최고 | 이긴 평균 / 진 평균 | 연속 손실 최대 |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
for nm, a, b in PER + (("전체", "20160101", "20991231"),):
    s = K[(K.day >= a) & (K.day <= b)].sort_values(["day", "t"]).rD; ls = (s <= 0).astype(int); run = (ls.groupby((ls == 0).cumsum()).cumsum()).max()
    P_("| %s | %d | %+.2f | %+.2f | %.0f%% | %+.1f | %+.1f | %+.1f | %+.1f | %+.1f | %+.1f / %+.1f | %d |" % (nm, len(s), s.mean(), s.median(), (s > 0).mean() * 100, s.quantile(.05), s.quantile(.01), s.min(), s.quantile(.95), s.max(), s[s > 0].mean(), s[s <= 0].mean(), run))
P_("\n## 3. 계좌(건당 고정 금액, 매수 = D+1 종가 · 매도 = D+3 종가, 비용 뒤)\n\n| 해 | 건 | 건당 | 승률 | 200만씩 손익(만) | 50만씩(만) |\n|---|---|---|---|---|---|")
for y, z in K.groupby(K.day.str[:4]):
    P_("| %s | %d | %+.2f%% | %.0f%% | %+.0f | %+.0f |" % (y, len(z), z.rD.mean(), (z.rD > 0).mean() * 100, z.rD.sum() * 2, z.rD.sum() * .5))
eq = (K.sort_values("day").groupby("day").rD.sum() * 2).cumsum(); dd = (eq - eq.cummax()).min()
conc = pd.Series(0, index=range(nd))
for i in K.i.values: conc[i + 1:i + 4] += 1
P_("\n합계 200만씩 %+.0f만 · 연 평균 %+.0f만 · 가장 깊은 낙폭 %.0f만 · 동시에 든 건수 평균 %.1f·최대 %d(= 최대 %d만 원 필요) · 든 날 비율 %.0f%%" % (
    eq.iloc[-1], eq.iloc[-1] / 10.9, dd, conc[conc > 0].mean(), conc.max(), conc.max() * 200, (conc > 0).mean() * 100))
c = sqlite3.connect("file:%s?mode=ro" % (BASE / "data" / "kospi.db"), uri=True); A1 = pd.read_sql("select ticker t, date d, amount a from daily where date>='20160101'", c); c.close()
c = sqlite3.connect("file:%s?mode=ro" % (BASE / "data" / "kosdaq.db"), uri=True); A2 = pd.read_sql("select ticker t, date d, volume*close a from daily where date>='20160101'", c); c.close()
am = pd.concat([A1, A2]); am["d"] = am.d.astype(str).str.replace("-", ""); am = am.drop_duplicates(["t", "d"]).set_index(["t", "d"]).a
K["a1"] = [am.get((t, cal[i + 1]), np.nan) for t, i in zip(K.t.values, K.i.values)]
K["d1"] = (K.c1 / K.c0 - 1) * 100
P_("\n## 4. 쪼개기(판 D)\n\n| 조건 | 학습 건 | 건당(중앙·승률) | 날 바구니(t) | 검증 건 | 건당(중앙·승률) | 날 바구니(t) |\n|---|---|---|---|---|---|---|")
SP = (("전체", K.rD > -999), ("D+1 거래대금 50억↑", K.a1 >= 5e9), ("10~50억", (K.a1 >= 1e9) & (K.a1 < 5e9)), ("유가증권", K.market == "유가증권"), ("코스닥", K.market == "코스닥"),
      ("1만원↑", K.c0 >= 10000), ("1만원↓", K.c0 < 10000), ("D+1 하루 등락 -10%↓", K.d1 <= -10), ("D+1 -10~-3%", (K.d1 > -10) & (K.d1 <= -3)), ("D+1 -3~+3%", (K.d1 > -3) & (K.d1 < 3)),
      ("D+1 +3~+10%", (K.d1 >= 3) & (K.d1 < 10)), ("D+1 +10%↑", K.d1 >= 10), ("5일 +15~40%", K.r5 < 40), ("5일 +40~70%", (K.r5 >= 40) & (K.r5 < 70)), ("5일 +70%↑", K.r5 >= 70),
      ("공시 16~17시(옛)", K.hm.str[:2].isin(["16", "17"])), ("공시 20시(요즘)", K.hm.str[:2] == "20"), ("그날 지정 1건", K.groupby("day").t.transform("size") == 1), ("그날 지정 2건↑", K.groupby("day").t.transform("size") >= 2))
for nm, m in SP:
    cells = []
    for _, a, b in PER:
        s = K[m & (K.day >= a) & (K.day <= b)]
        if len(s) < 15: cells.append("%d | – | –" % len(s)); continue
        d = s.groupby("day").rD.mean(); cells.append("%d | %+.2f%% (%+.2f·%.0f%%) | %+.2f%% (t%.1f)" % (len(s), s.rD.mean(), s.rD.median(), (s.rD > 0).mean() * 100, d.mean(), t_(d)))
    P_("| %s | %s | %s |" % (nm, cells[0], cells[1]))
P_("\n## 5. 반년씩(판 D 건당 · 건)\n")
K["hf"] = K.day.str[:4] + np.where(K.day.str[4:6] <= "06", "상", "하")
P_(" · ".join("%s %+.1f(%d)" % (h, z.rD.mean(), len(z)) for h, z in K.groupby("hf")))
K.to_pickle("C:/temp/kp/heat_ev3.pkl")
(BASE / "research" / "reports" / "heat3_1117.md").write_text("\n".join(OUT), encoding="utf-8")
