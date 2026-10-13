# -*- coding: utf-8 -*-
"""T1 '그물은 넓게, 체결은 엄격하게' (2026-10-13 사용자: "못 산 것들까지 샀다면 이득이 좋았잖아 — 매수 쪽에서 조정 가능한 방식 없어?").

예상가가 얕게 빗나가 아침 후보에 못 든 종목도 실제로 깊게 열리면 사게: 후보 조건(예상 갭 하위 q · 예상 시장 대비 c)을 넓히고
지정가 문턱(시장 대비 L, 실제 시가가 그 아래일 때만 체결)으로 거른다. 오차 = 3일 실측 오차 × 0.55(실측 적중 45% 에 맞춘 배율), 20번 평균.
비교 기준 = 지금(q 10% · c -2 · L -0.75). 학습 2016~22 · 검증 2023~2026-08, 한 건 150만원 · 시가 체결만 · 그날 종가 매도.
    python research/t1_widen.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "factory"))
import numpy as np, pandas as pd
import lab, feats as FT, common as C

AMT, SCALE, NSIM = 1_500_000, 0.55, 20
E = pd.read_pickle(C.CACHE / "gap_err_3d.pkl")
ERR = {k: (g.gx - g.gr).values for k, g in E.groupby("tiny")}
U = lab.hist()
U = U[U.oc.notna() & U.gap.notna() & (U.date >= "20160101")][["ticker", "date", "gap", "q_vm", "liq", "oc"]].reset_index(drop=True)
dcode = pd.factorize(U.date)[0]
tiny = (U.liq <= 1 / 3).values
gr = U.gap.values
oc = np.clip(U.oc.values, -60, 60) - FT.COST
TR = (U.date <= "20221231").values; VA = (U.date >= "20230101").values
NY = {"학습": 7.0, "검증": len(set(U.date[VA])) / 245.0}
med = lambda x: pd.Series(x).groupby(dcode).transform("median").values
rank = lambda x: pd.Series(x).groupby(dcode).rank(pct=True).values
real_rel = gr - med(gr)
quiet = (U.q_vm.values <= 0.30) & tiny
rng = np.random.default_rng(9)
SIMS = []
for k in range(NSIM):
    gx = gr.copy()
    for t in (False, True):
        m = tiny == t
        gx[m] = gr[m] + SCALE * rng.choice(ERR[t], m.sum())
    SIMS.append((rank(gx), gx - med(gx), med(gx)))
real_t1 = quiet & (rank(gr) <= 0.10) & (real_rel <= -2)

V = [("지금: 후보 하위10%·-2 / 지정가 -0.75", 0.10, -2.0, -0.75)]
for q in (0.10, 0.15, 0.20):
    for c in (-2.0, -1.5, -1.0, -0.5):
        for L in (-0.75, -1.5, -2.0):
            if (q, c, L) == (0.10, -2.0, -0.75): continue
            V.append(("후보 하위%d%%·%+.1f / 지정가 %+.2f" % (q * 100, c, L), q, c, L))
res = []
for nm, q, c, L in V:
    acc = {"학습": [], "검증": []}
    for qx, rx, mg in SIMS:
        cand = quiet & (qx <= q) & (rx <= c)
        fill = cand & (gr <= mg + L)                      # 실제 시가 ≤ 지정가(어제 종가 × (1 + 예상 시장 갭 + L))
        for per, pm in (("학습", TR), ("검증", VA)):
            x = oc[fill & pm]
            acc[per].append((len(x), x.mean() if len(x) else np.nan, (x > 0).mean() * 100 if len(x) else np.nan, x.sum(),
                             (fill & pm & real_t1).sum() / max((real_t1 & pm).sum(), 1) * 100, (cand & pm).sum()))
    a = {p: np.array(v).mean(0) for p, v in acc.items()}
    res.append((nm, a))
print("| 방식 | 학습 연 건수 · 평균 · 승률 · 연 수익금 | 검증 연 건수 · 평균 · 승률 · 연 수익금 | 진짜 T1 잡은 비율(검증) | 하루 주문 수(검증) |")
print("|---|---|---|---|---|")
base = res[0][1]["검증"][3]
for nm, a in sorted(res, key=lambda r: -r[1]["검증"][3])[:14] + [res[0]]:
    t, v = a["학습"], a["검증"]
    print("| %s | %.0f건 · %+.2f%% · %.0f%% · %.0f만 | %.0f건 · %+.2f%% · %.0f%% · **%.0f만** | %.0f%% | %.1f |" % (
        nm, t[0] / NY["학습"], t[1], t[2], t[3] / 100 * AMT / NY["학습"] / 1e4, v[0] / NY["검증"], v[1], v[2], v[3] / 100 * AMT / NY["검증"] / 1e4, v[4], v[5] / (NY["검증"] * 245)))
