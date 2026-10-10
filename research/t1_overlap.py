# -*- coding: utf-8 -*-
"""T2·T3 겹칠 때 둘 다 사기(총 3배) — 2026-10-11 사용자 "겹치면 t-1만 사게 되어 있는데 둘 다 사면?"

(아래는 t1_limit_ext.py 설명) T1 지정가 전환이 덤 규칙(T1-1 = T2 어제 막판 약세 · T1-2 = T3 짝 미장 하락)에 주는 영향 (2026-10-11 사용자).

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
THRS = [-1.0, -1.25, -1.5, -1.75, -2.0, -2.5, -3.0]
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
t3 = U.tr_pred.values <= -0.5
both = t2 & t3
yr = U.date.str[:4].values
real_r = {}
R = {}
for c, mg in SIMS:
    variants = {"시장가(지금)": c, "문턱 -1": c & (op <= pc * (1 + (mg - 1.0) / 100))}
    for nm, m in variants.items():
        for rule, rm in (("T2만(T3 아님)", m & t2 & ~t3), ("T3만(T2 아님)", m & t3 & ~t2), ("겹침(T2&T3)", m & both)):
            x = oc[rm]
            R.setdefault((nm, rule), []).append((len(x), x.mean() if len(x) else np.nan, (x > 0).mean() * 100 if len(x) else np.nan,
                                                  x.sum(), np.percentile(x, 5) if len(x) > 5 else np.nan, x.min() if len(x) else np.nan))
print("\n### 검증 2023-01~2026-08 · 한 건 150만원 · 시가 체결")
print("| 방식 | 묶음 | 연 건수 | 평균 | 승률 | 한 번 살 때 연 수익금 | 나쁜 5% 거래 | 최악 |")
print("|---|---|---|---|---|---|---|---|")
for nm in ("시장가(지금)", "문턱 -1"):
    for rule in ("T2만(T3 아님)", "T3만(T2 아님)", "겹침(T2&T3)"):
        a = np.array(R[(nm, rule)]).mean(0)
        print("| %s | %s | %.0f | %+.2f%% | %.0f%% | %+.0f만 | %+.1f%% | %+.1f%% |" % (nm, rule, a[0] / NY, a[1], a[2], a[3] / 100 * AMT / NY / 1e4, a[4], a[5]))
print("\n연구판(실제 갭으로 고른 T1) 겹침 해마다:")
for y in sorted(set(yr)):
    x = oc[real & both & (yr == y)]
    if len(x): print("  %s: %d건 %+.2f%% 승률 %.0f%% 최악 %+.1f%%" % (y, len(x), x.mean(), (x > 0).mean() * 100, x.min()))
x = oc[real & both]; z = oc[real & t2 & ~t3]; w = oc[real & t3 & ~t2]
print("연구판 합: 겹침 %d건 %+.2f%% · T2만 %d건 %+.2f%% · T3만 %d건 %+.2f%%" % (len(x), x.mean(), len(z), z.mean(), len(w), w.mean()))
for nm in ("시장가(지금)", "문턱 -1"):
    a = np.array(R[(nm, "겹침(T2&T3)")]).mean(0)
    print("%s: 겹칠 때 3배로 바꾸면 연 %+.0f만원 더(연 %.0f건 × 150만원 × %+.2f%%) · 그날 그 종목 450만원 → 최악 거래면 %+.0f만원" % (
        nm, a[3] / 100 * AMT / NY / 1e4, a[0] / NY, a[1], a[5] / 100 * AMT * 3 / 1e4))
