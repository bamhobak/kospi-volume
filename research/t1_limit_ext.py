# -*- coding: utf-8 -*-
"""T1 지정가 전환이 덤 규칙(T1-1 = T2 어제 막판 약세 · T1-2 = T3 짝 미장 하락)에 주는 영향 (2026-10-11 사용자).

실전: 예상 갭으로 고른 T1 후보 중 T2(어제 14:00→종가 ≤ -1%)면 한 번 더, 아니고 T3(짝 미장 예상 갭 ≤ -0.5)면 한 번 더 산다.
→ 덤도 같은 예상 오차를 물려받는다. t1_limit.py 와 같은 시뮬(오차 배율 0.55 = 3일 실측 적중 45%)에
  T2·T3 표시를 붙여 시장가 vs 문턱 지정가(시가에만 체결)를 규칙별로 잰다. T2 는 어제 1분봉이 필요해 2023~ 만.
    python research/t1_limit_ext.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "factory"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import lab, feats as FT, common as C
import m1_event as ME

AMT = 1_500_000
SCALE, NSIM = 0.55, 10
THRS = [float(x) for x in sys.argv[1].split(",")] if len(sys.argv) > 1 else [-1.0, -1.25, -1.5, -1.75, -2.0, -2.5, -3.0]
E = pd.read_pickle(C.CACHE / "gap_err_3d.pkl")
ERR = {k: (g.gx - g.gr).values for k, g in E.groupby("tiny")}

U = lab.hist()
U = U[U.oc.notna() & U.gap.notna() & (U.date >= "20230101")][["ticker", "date", "gap", "q_vm", "liq", "oc", "px", "tr_pred"]]
P = pd.read_pickle(C.CACHE / "factory_px.pkl")[["ticker", "date", "open"]].sort_values(["ticker", "date"])
P["pdate"] = P.groupby("ticker").date.shift(1)
U = U.merge(P, on=["ticker", "date"]).reset_index(drop=True)
dcode = pd.factorize(U.date)[0]
tiny = (U.liq <= 1 / 3).values
gr, pc, op = U.gap.values, U.px.values, U.open.values
oc = np.clip(U.oc.values, -60, 60) - FT.COST
NY = len(set(U.date)) / 245.0


def med_by_day(x):
    return pd.Series(x).groupby(dcode).transform("median").values


def pick(gx):
    q = pd.Series(gx).groupby(dcode).rank(pct=True).values
    return (q <= 0.10) & (U.q_vm.values <= 0.30) & tiny & (gx - med_by_day(gx) <= -2.0)


rng = np.random.default_rng(5)
SIMS = []
for k in range(NSIM):
    gx = gr.copy()
    for t in (False, True):
        m = tiny == t
        gx[m] = gr[m] + SCALE * rng.choice(ERR[t], m.sum())
    SIMS.append((pick(gx), med_by_day(gx)))
real = pick(gr)
anyc = np.zeros(len(U), bool)
for c, _ in SIMS: anyc |= c
anyc |= real
need = U[anyc & U.pdate.notna()]
print("후보(시뮬 %d번 + 연구 T1) 종목-일 %d → 어제 1분봉 받기" % (NSIM, len(need)), flush=True)
got, miss = ME.ensure("KR", list(zip(need.ticker, need.pdate)), log=lambda *a: print(*a, flush=True))
print("받음 %d · 못 받음 %d" % (got, miss), flush=True)
lh = np.full(len(U), np.nan)
for t, g in need.groupby("ticker"):
    B = ME.bars("KR", t, list(g.pdate))
    for i, r in zip(g.index, g.itertuples()):
        b = B.get(r.pdate)
        if b is None or not len(b): continue
        b14 = b[b.hm <= "1400"]
        if len(b14): lh[i] = (b.c.iloc[-1] / b14.c.iloc[-1] - 1) * 100
t2 = lh <= -1.0
t3 = (U.tr_pred.values <= -0.5) & ~t2
print("어제 1분봉 있는 후보 비율 %.0f%%\n" % (np.isfinite(lh[anyc]).mean() * 100))

R = {}
for c, mg in SIMS:
    variants = {"시장가(지금)": c}
    for th in THRS:
        variants["문턱 %+.2f" % th] = c & (op <= pc * (1 + (mg + th) / 100))
    for nm, m in variants.items():
        for rule, rm in (("T1", m), ("T1-1(T2)", m & t2), ("T1-2(T3)", m & t3)):
            x = oc[rm]
            R.setdefault((nm, rule), []).append((len(x), x.mean() if len(x) else np.nan, (x > 0).mean() * 100 if len(x) else np.nan, x.sum()))

for rule, rm in (("T1", real), ("T1-1(T2)", real & t2), ("T1-2(T3)", real & t3)):
    x = oc[rm]
    print("참고 연구판(실제 갭으로 고름) %s: 연 %.0f건 %+.2f%% 승률 %.0f%% → 연 %.0f만원" % (rule, len(x) / NY, x.mean(), (x > 0).mean() * 100, x.sum() / 100 * AMT / NY / 1e4))
print("\n### 검증 2023-01~2026-08 · 한 건 150만원 · 시가에만 체결(장중 체결 없음)")
print("| 방식 | T1 연 건수·평균·승률·수익금 | T1-1(T2) 덤 | T1-2(T3) 덤 | 셋 합계 연 수익금 |")
print("|---|---|---|---|---|")
for nm in ["시장가(지금)"] + ["문턱 %+.2f" % t for t in THRS]:
    cells, tot = [], 0
    for rule in ("T1", "T1-1(T2)", "T1-2(T3)"):
        a = np.array(R[(nm, rule)]).mean(0)
        won = a[3] / 100 * AMT / NY / 1e4; tot += won
        cells.append("%.0f건 · %+.2f%% · %.0f%% · %+.0f만" % (a[0] / NY, a[1], a[2], won))
    print("| %s | %s | %s | %s | **%+.0f만원** |" % (nm, *cells, tot))
