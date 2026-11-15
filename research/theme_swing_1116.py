# -*- coding: utf-8 -*-
"""같은 테마(업종) 안에서 더 빠진·더 오른 종목 — 기간 수익률로 스윙 조건 (2026-11-16 사용자 "장전 데이터 말고 기간 데이터로 체크해서 스윙 조건으로 적당한지").
자료: quiet_break_1112.load()(kospi.db·kosdaq.db·폐지 포함 일봉 2005~2026-09) · 묶음 ⓐ 테마 2026-08-28 명단(4~60종목, **한 장을 과거에 씌움 — 지금 테마에 남은 종목만이라 절대 수익이 부풀 수 있다**)
      ⓑ 업종 분기별 명단(2014~, 41개 — 그날 기준 가장 최근 명단, 편향 없음).
신호: 5거래일마다(겹침 줄이기) · 유니버스 종가 1천원↑·20일 거래대금 3억↑ · 묶음 안 4종목↑.
  묶음 수익 = 구성 종목 L일 수익률 중앙(L = 5·20·60) · 상대 = 종목 − 묶음. 문턱 X = 5·10·20%(L 따라).
  날: 묶음이 뜸(≥ +X) · 빠짐(≤ −X) · 아무 때 × 고르기: 가장 뒤처진 1종목 · 가장 앞선 1종목 · 묶음보다 X%p↓ · X%p↑
매수 = 신호 날 종가 → H일 뒤 종가(H = 5·20·60) · 비용 0.23. 대조: 같은 날 시장 평균 · 같은 묶음 나머지 평균. 학습 2016~22 · 검증 2023~.
    python research/memguard.py research/theme_swing_1116.py
"""
import math, sqlite3, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path[:0] = [str(ROOT)]; sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import quiet_break_1112 as Q
OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))
PER = (("20160101", "20221231"), ("20230101", "20991231"))
t_ = lambda s: s.mean() / s.std(ddof=1) * math.sqrt(len(s)) if len(s) > 2 and s.std(ddof=1) > 0 else 0
D = Q.build(Q.load())
days = sorted(D.date.unique()); dix = {d: i for i, d in enumerate(days)}; D["di"] = D.date.map(dix)
cs = D.lr.groupby(D.ticker).cumsum()
for L in (5, 20, 60): D["r%d" % L] = ((np.exp(cs - cs.groupby(D.ticker).shift(L)) - 1) * 100).astype("float32")
D = D[(D.date >= "20150101") & (D.di % 5 == 0) & (D.close >= 1000) & (D.a20 >= 3e8)][["ticker", "date", "r5", "r20", "r60", "f5", "f20", "f60"]].reset_index(drop=True)
for h in (5, 20, 60): D["m%d" % h] = D.groupby("date")["f%d" % h].transform("mean")
c = sqlite3.connect("file:" + str(BASE / "data" / "kospi.db") + "?mode=ro", uri=True)
S = pd.read_sql("select snap, kind, gid, ticker from sector", c)


def study(ko, X):
    P("\n## %s — 묶음-날 %d · 종목-일 %d\n" % (ko, X.groupby(["date", "g"]).ngroups, len(X)))
    P("| 기간 L | 묶음 상태 | 고르는 종목 | 보유 | 학습 건·날 | 학습 건당 | 날 바구니(t) | 시장 대비 | 같은 묶음 대비(t) | 검증 건·날 | 검증 건당 | 날 바구니(t) | 시장 대비 | 같은 묶음 대비(t) |"); P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for L, Xc in ((5, 5), (20, 10), (60, 20)):
        r = "r%d" % L
        Y = X.dropna(subset=[r]).copy()
        g = Y.groupby(["date", "g"])
        Y["n"] = g.ticker.transform("size"); Y = Y[Y.n >= 4]; g = Y.groupby(["date", "g"])
        Y["tg"] = g[r].transform("median"); Y["rel"] = Y[r] - Y.tg
        Y["lo"] = g[r].rank(method="first"); Y["hi"] = g[r].rank(method="first", ascending=False)
        for h in (5, 20, 60):
            f = "f%d" % h; s, n = g[f].transform("sum"), g[f].transform("count")
            Y["p%d" % h] = (s - Y[f].fillna(0)) / (n - Y[f].notna()).replace(0, np.nan)
        for dn, dm in (("뜸(+%d%%↑)" % Xc, Y.tg >= Xc), ("빠짐(-%d%%↓)" % Xc, Y.tg <= -Xc), ("아무 때", Y.tg > -999)):
            for pn, pm in (("가장 뒤처진 1종목", Y.lo == 1), ("가장 앞선 1종목", Y.hi == 1), ("묶음보다 %d%%p↓" % Xc, Y.rel <= -Xc), ("묶음보다 %d%%p↑" % Xc, Y.rel >= Xc)):
                Z = Y[dm & pm].drop_duplicates(["ticker", "date"])
                for h in (5, 20, 60):
                    f = "f%d" % h; cells = []
                    for a, b in PER:
                        z = Z[(Z.date >= a) & (Z.date <= b)].dropna(subset=[f])
                        if len(z) < 30: cells = None; break
                        d = z.groupby("date")[f].mean(); e = z.assign(e=z[f] - z["p%d" % h]).groupby("date").e.mean().dropna()
                        cells.append("%d·%d | %+.2f%% | %+.2f%% (%.1f) | %+.2f | %+.2f (%.1f)" % (len(z), len(d), z[f].mean(), d.mean(), t_(d), (z[f] - z["m%d" % h]).mean(), e.mean(), t_(e)))
                    if cells: P("| %d일 | %s | %s | %d일 | %s | %s |" % (L, dn, pn, h, cells[0], cells[1]))


T = S[(S.snap == "20260828") & (S.kind == "theme")]
T = T[T.groupby("gid").ticker.transform("size").between(4, 60)].assign(g=lambda z: z.gid.astype(str))
study("ⓐ 테마(2026-08-28 명단을 과거에 씌움 — 절대 수익은 부풀 수 있음, '같은 묶음 대비'를 볼 것)", D.merge(T[["g", "ticker"]], on="ticker"))
Uq = S[(S.kind == "upjong") & (S.snap < "20260828")]
snaps = sorted(Uq.snap.unique())
dd = pd.DataFrame({"date": sorted(D.date.unique())}); dd["snap"] = [max([s for s in snaps if s <= d], default=None) for d in dd.date]
Xu = D.merge(dd, on="date").merge(Uq[["snap", "gid", "ticker"]].rename(columns={"gid": "g"}), on=["snap", "ticker"])
study("ⓑ 업종(그날 기준 분기 명단 41개 — 편향 없음)", Xu)
(ROOT / "theme_swing_1116.out").write_text("\n".join(OUT), encoding="utf-8")
