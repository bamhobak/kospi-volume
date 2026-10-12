# -*- coding: utf-8 -*-
"""T1 시장 급락일 들고 가기 (2026-10-12 사용자: "장 자체가 극단적으로 안 좋을 때 그날 종가에 안 팔고 다음날 종가에 팔면 더 나은지").

시장 상태 = 그날 유니버스 종목들 시가→종가 중앙값(%) — 15:19 쯤이면 거의 안다(종가 단일가 전).
T1(·T2 근사 없음·T3) 시가 매수 → ① 그날 종가 ② 다음날 시가 ③ 다음날 종가 매도 비교, 비용 0.23 한 번.
학습 2016~22 · 검증 2023~2026-08.
    python research/t1_badday_hold.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "factory"))
import numpy as np, pandas as pd
import lab, feats as FT, common as C

U = lab.hist().sort_values(["ticker", "date"]).reset_index(drop=True)
OK = U.oc.notna()
U["mkt"] = U.date.map(U[OK].groupby("date").oc.median())                     # 그날 시장(유니버스 중앙) 시가→종가
P = pd.read_pickle(C.CACHE / "factory_px.pkl").sort_values(["ticker", "date"])
g = P.groupby("ticker", sort=False)
P["no"] = g.open.shift(-1); P["nc"] = g.close.shift(-1)
W = U[["ticker", "date"]].merge(P[["ticker", "date", "open", "close", "no", "nc"]], how="left", on=["ticker", "date"])
o, cl, no, nc = W.open.values, W.close.values, W.no.values, W.nc.values
U["r_c"] = np.clip(U.oc.values, -60, 60) - FT.COST
U["r_no"] = np.clip((no / o - 1) * 100, -60, 60) - FT.COST
U["r_nc"] = np.clip((nc / o - 1) * 100, -60, 60) - FT.COST
U["nmkt"] = U.date.map(dict(zip(sorted(U.date.unique()), list(pd.Series(sorted(U.date.unique())).shift(-1)))))
U["nmkt"] = U.nmkt.map(U[OK].groupby("date").oc.median())                     # 다음날 시장(참고)
T1 = U.t1 & OK & U.r_nc.notna()
T3 = T1 & (U.tr_pred <= -0.5)
BINS = [(-99, -3), (-3, -2), (-2, -1), (-1, 0), (0, 99)]


def show(nm, base):
    print("\n### %s" % nm)
    print("| 그날 시장(중앙 시가→종가) | 구간 | 건수 | 그날 종가 | 다음날 시가 | 다음날 종가 | 승률(그날/다음날 종가) | 다음날 시장 평균 |")
    print("|---|---|---|---|---|---|---|---|")
    for per, (a, b) in (("학습", lab.TR), ("검증", lab.VA)):
        for lo, hi in BINS:
            x = U[base & (U.date >= a) & (U.date <= b) & (U.mkt > lo) & (U.mkt <= hi)]
            if not len(x): continue
            print("| %s ~ %s%% | %s | %d (%d일) | %+.2f%% | %+.2f%% | %+.2f%% | %.0f%% / %.0f%% | %+.2f%% |" % (
                "%+d" % lo if lo > -99 else "", "%+d" % hi if hi < 99 else "", per, len(x), x.date.nunique(),
                x.r_c.mean(), x.r_no.mean(), x.r_nc.mean(), (x.r_c > 0).mean() * 100, (x.r_nc > 0).mean() * 100, x.nmkt.mean()))


show("T1 [갭 하락 조용주]", T1)
show("T3 [갭 하락 조용주 ++] (짝 미장 하락)", T3)
print("\n그날 T1 이 이미 손해(그날 종가 기준 < 0)인 것만, 시장 ≤ -2% 날:")
for per, (a, b) in (("학습", lab.TR), ("검증", lab.VA)):
    x = U[T1 & (U.date >= a) & (U.date <= b) & (U.mkt <= -2) & (U.r_c < 0)]
    print("  %s %d건: 그날 종가 %+.2f%% → 다음날 시가 %+.2f%% · 다음날 종가 %+.2f%%" % (per, len(x), x.r_c.mean(), x.r_no.mean(), x.r_nc.mean()))
print("\n해마다(시장 ≤ -2% 날 T1): 그날 종가 vs 다음날 종가")
x = U[T1 & (U.mkt <= -2)]
for y, gy in x.groupby(x.date.str[:4]):
    print("  %s: %3d건  %+.2f%% → %+.2f%%" % (y, len(gy), gy.r_c.mean(), gy.r_nc.mean()))
