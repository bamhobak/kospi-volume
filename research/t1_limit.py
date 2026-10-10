# -*- coding: utf-8 -*-
"""T1 지정가 문턱 비교 (2026-10-11 사용자: "장중에 9800원 닿은 거 구매했을 때도 수익률 체크해 보고,
-1 -1.25 -1.5 -1.75 -2 -2.5 -3 모든 조건 다 같은 금액으로 매수했다고 쳤을 때 수익률이랑 수익금 비교").

후보 = 지금 실전처럼 '예상 갭'으로 고른 T1 (예상 오차 = 데이 스냅샷 3일 실측 오차를 과거에 입힘, 20번 평균).
지정가 = 어제 종가 × (1 + 예상 시장 갭 + 문턱).  체결:
  · 시가 체결: 실제 시가 ≤ 지정가 → 시가에 삼
  · 장중 체결: 시가는 위였는데 장중 저가가 지정가 아래로 내려옴 → 지정가에 삼
둘 다 그날 종가 매도, 비용 0.23%, 한 건 150만 원. 학습 2016~22 · 검증 2023~2026-08.
    python research/t1_limit.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "factory"))
import numpy as np, pandas as pd
import lab, feats as FT, common as C

AMT = 1_500_000
THRS = [-1.0, -1.25, -1.5, -1.75, -2.0, -2.5, -3.0]
E = pd.read_pickle(C.CACHE / "gap_err_3d.pkl")
ERR = {k: (g.gx - g.gr).values for k, g in E.groupby("tiny")}         # 실측 오차(예상 갭 - 실제 갭), 유동성 아래/위 따로

U = lab.hist()
U = U[U.oc.notna() & U.gap.notna()][["ticker", "date", "gap", "q_vm", "liq", "oc", "px"]]
P = pd.read_pickle(C.CACHE / "factory_px.pkl")[["ticker", "date", "open", "low", "close"]]
U = U.merge(P, on=["ticker", "date"]).reset_index(drop=True)
U = U[(U.date >= "20160101")].reset_index(drop=True)
dcode = pd.factorize(U.date)[0]
tiny = (U.liq <= 1 / 3).values
gr = U.gap.values                                                        # 실제 시가 갭(%)
pc, op, lo, cl = U.px.values, U.open.values, U.low.values, U.close.values
oc = np.clip(U.oc.values, -60, 60) - FT.COST
yr = U.date.str[:4].values
TR = (U.date <= "20221231").values; VA = (U.date >= "20230101").values
NY = {"학습": 7.0, "검증": len(set(U.date[VA])) / 245.0}
rng = np.random.default_rng(5)


def med_by_day(x):
    return pd.Series(x).groupby(dcode).transform("median").values


def pick(gx):
    q = pd.Series(gx).groupby(dcode).rank(pct=True).values
    rel = gx - med_by_day(gx)
    return (q <= 0.10) & (U.q_vm.values <= 0.30) & tiny & (rel <= -2.0)


real_pick = pick(gr)
SCALE = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0           # 오차 크기 배율 — 3일 실측(실제도 ≤-2 45%)에 맞추려고
R = {}
calib = []
for k in range(20):
    gx = gr.copy()
    for t in (False, True):
        m = tiny == t
        gx[m] = gr[m] + SCALE * rng.choice(ERR[t], m.sum())
    cand = pick(gx)
    mg = med_by_day(gx)                                                  # 예상 시장 갭(그날 예상 갭 중앙)
    rr = gr - med_by_day(gr)
    calib.append(((rr[cand & tiny] <= -2).mean() * 100, (rr[cand & tiny] <= -1).mean() * 100, cand.sum() / len(set(U.date))))
    res = {"시장가(지금)": (cand, oc, np.zeros(len(U), bool))}
    for th in THRS:
        lim = pc * (1 + (mg + th) / 100)
        f_open = cand & (op <= lim)
        f_intra = cand & (op > lim) & (lo < lim)                         # 닿기만 한 건 못 샀다고 보수적으로(저가가 지정가 '아래'일 때만)
        r = np.where(f_open, oc, np.where(f_intra, (cl / lim - 1) * 100 - FT.COST, np.nan))
        res["문턱 %+.2f" % th] = (f_open | f_intra, r, f_intra)
    for nm, (m, r, fi) in res.items():
        for per, pm in (("학습", TR), ("검증", VA)):
            for part, pp in (("전체", m), ("시가", m & ~fi), ("장중", m & fi)):
                x = r[pp & pm]
                R.setdefault((nm, per, part), []).append((len(x), np.nanmean(x) if len(x) else np.nan, (x > 0).mean() * 100 if len(x) else np.nan, np.nansum(x)))

c = np.array(calib).mean(0)
print("오차 배율 %.2f: 예상으로 고른 후보 중 실제도 시장 대비 ≤-2 %.0f%% · ≤-1 %.0f%% (3일 실측 45%% · 71%%) · 하루 후보 %.1f개(실측 3~6)" % (SCALE, *c))
x = oc[real_pick & VA]
print("참고 연구 T1(실제 갭으로 고름, 시가 매수): 검증 연 %.0f건 %+.2f%% → 연 %.0f만원 (150만원씩)\n" % (len(x) / NY["검증"], x.mean(), x.sum() / 100 * AMT / NY["검증"] / 1e4))


def show(per):
    print("### %s (%s)" % (per, "2016~2022" if per == "학습" else "2023-01~2026-08"))
    print("| 방식 | 시가에만 사기: 연 건수 · 평균 · 승률 · 연 수익금 | 장중 닿은 것까지: 연 건수 · 평균 · 승률 · 연 수익금 | 장중 몫만: 연 건수 · 평균 |")
    print("|---|---|---|---|")
    ny = NY[per]
    for nm in ["시장가(지금)"] + ["문턱 %+.2f" % t for t in THRS]:
        a = np.array(R[(nm, per, "전체")]).mean(0); o = np.array(R[(nm, per, "시가")]).mean(0); i = np.array(R[(nm, per, "장중")]).mean(0)
        won = lambda z: z[3] / 100 * AMT / ny / 1e4
        intra = "-" if nm.startswith("시장가") else "%.0f건 · %+.2f%% · %.0f%% · **%+.0f만원**" % (a[0] / ny, a[1], a[2], won(a))
        ip = "-" if not i[0] else "%.0f건 · %+.2f%%" % (i[0] / ny, i[1])
        print("| %s | %.0f건 · %+.2f%% · %.0f%% · **%+.0f만원** | %s | %s |" % (nm, o[0] / ny, o[1], o[2], won(o), intra, ip))
    print()


show("검증"); show("학습")
