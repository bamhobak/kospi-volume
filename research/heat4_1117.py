# -*- coding: utf-8 -*-
"""H0425 [단기과열 단일가] 덧조건 다각도 (2026-11-17 사용자 "이전 움직임·외국인 매수량 증가 여부·거래대금 이런 거 붙여서 더 수익금 좋게").
판 D(D+1 종가 → D+3 종가) 1,191건에 재료를 붙여 3등분(경계는 학습 기간으로 정함) → 학습·검증 건당·승률·200만씩 손익.
쓸 수 있는 재료 = 사는 순간(D+1 종가 직전)까지 아는 것. 외국인·기관 수급은 D 까지(D+1 수급은 장 끝나야 나옴).
'통과' = 학습·검증 같은 방향 + 가운데 칸이 사이에 있음(한 줄로 늘어섬) + 위·아래 차이 날 바구니 t ≥ 2(학습)·≥ 1(검증).
"""
import math, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parent.parent
OUT = []; P_ = lambda s="": (OUT.append(s), print(s, flush=True))
t_ = lambda s: s.mean() / s.std(ddof=1) * math.sqrt(len(s)) if len(s) > 2 and s.std(ddof=1) > 0 else 0.0
K = pd.read_pickle("C:/temp/kp/heat_ev3.pkl").reset_index(drop=True)
S = pd.read_pickle(BASE / "data" / "kr_scan.pkl")
S = S[S.ticker.isin(set(K.t)) & (S.date >= "20150101")][["date", "ticker", "close", "volume", "amt20", "ret3", "ret5", "ret10", "ret20", "ret60", "ret120", "ret250", "fromhi", "fromlo", "vol20", "marcap", "PBR", "mk", "dma60"]].copy()
S = S.sort_values(["ticker", "date"]); S["amt"] = S.close * S.volume / 1e8
g = S.groupby("ticker", sort=False)
S["ret1"] = g.close.pct_change() * 100; S["amt_1"] = g.amt.shift(-1); S["amt_p5"] = g.amt.transform(lambda s: s.rolling(5).mean()); S["amt_p60"] = g.amt.transform(lambda s: s.shift(5).rolling(60, min_periods=20).mean())
S["up5"] = g.ret1.transform(lambda s: (s > 0).rolling(5).sum()); S["lim5"] = g.ret1.transform(lambda s: (s >= 29).rolling(5).sum())
c = sqlite3.connect("file:%s?mode=ro" % (BASE / "data" / "investor.db"), uri=True)
print(c.execute("select min(date), max(date), count(*) from flow11").fetchone(), [r[1] for r in c.execute("pragma table_info(flow11)")])
F = pd.read_sql("SELECT ticker, date, frgn, fin+ins+tru+pef+bank+ofin+pens AS inst, indiv FROM flow11 WHERE date >= '20150101'", c); c.close()
F = F[F.ticker.isin(set(K.t))]; S = S.merge(F, on=["ticker", "date"], how="left")
print("수급 단위 확인(중앙 |frgn|):", F.frgn.abs().median())
g = S.groupby("ticker", sort=False)
for k in ("frgn", "inst", "indiv"):
    for w in (1, 5, 20): S["%s%d" % ({"frgn": "f", "inst": "i", "indiv": "n"}[k], w)] = g[k].transform(lambda s: s.rolling(w, min_periods=w).sum())
pos = (S.frgn > 0).astype(int); S["fup5"] = pos.groupby(S.ticker).transform(lambda s: s.rolling(5).sum())
# 수급을 크기로 나눔: 금액이면 거래대금 대비, 주수면 거래량 대비 → 5일 거래대금(억) 대비 % (단위는 위 중앙값으로 판단)
X = K.merge(S.rename(columns={"ticker": "t", "date": "day"}), on=["t", "day"], how="left")
unit_won = F.frgn.abs().median() > 1e6
den5 = X.amt_p5 * 5 * 1e8 if unit_won else g.volume.transform(lambda s: s.rolling(5).sum()).reindex(S.index).values[S.set_index(["ticker", "date"]).index.get_indexer(list(zip(X.t, X.day)))]
den1 = X.amt * 1e8 if unit_won else X.volume
for k in ("f", "i", "n"):
    X[k + "5p"] = X[k + "5"] / den5 * 100; X[k + "1p"] = X[k + "1"] / den1 * 100
X["f20p"] = X.f20 / (X.amt_p60 * 20 * 1e8 if unit_won else np.nan) * 100
X["gap1"] = (X.o1 / X.c0 - 1) * 100; X["in1"] = (X.c1 / X.o1 - 1) * 100; X["pos1"] = (X.c1 - X.l1) / (X.h1 - X.l1).replace(0, np.nan)
X["a1e"] = X.a1 / 1e8; X["a1_a0"] = X.a1e / X.amt; X["a0_p60"] = X.amt / X.amt_p60; X["turn1"] = X.a1 / X.marcap * 100; X["mc"] = X.marcap / 1e8
X["nday"] = X.groupby("day").t.transform("size"); X["wd"] = pd.to_datetime(X.day).dt.weekday
ev = X.sort_values(["t", "i"]); X["prev"] = ev.groupby("t").i.diff().reindex(X.index); X["again"] = (X.prev <= 250).astype(float)
PER = (("학습", "20160101", "20221231"), ("검증", "20230101", "20991231"))
L = X.day <= "20221231"
FEAT = (("지정 날(D) 등락률", "ret1"), ("3일 등락", "ret3"), ("5일 등락", "ret5"), ("10일 등락", "ret10"), ("20일 등락", "ret20"), ("60일 등락", "ret60"), ("120일 등락", "ret120"), ("250일 등락", "ret250"),
        ("5일 중 오른 날 수", "up5"), ("60일선 이격", "dma60"), ("1년 고점 대비", "fromhi"), ("20일 변동성", "vol20"),
        ("D+1 시가 갭", "gap1"), ("D+1 장중(시가→종가)", "in1"), ("D+1 하루 등락", "d1"), ("D+1 종가 위치(저0~고1)", "pos1"),
        ("D+1 거래대금(억)", "a1e"), ("D+1 ÷ D 거래대금", "a1_a0"), ("D 거래대금 ÷ 평소 60일", "a0_p60"), ("D+1 회전율(%)", "turn1"), ("20일 평균 거래대금", "amt20"), ("시가총액(억)", "mc"), ("주가", "c0"), ("PBR", "PBR"),
        ("외국인 D 순매수(거래 대비 %)", "f1p"), ("외국인 5일 순매수(%)", "f5p"), ("외국인 20일 순매수(%)", "f20p"), ("외국인 5일 중 산 날 수", "fup5"), ("기관 D 순매수(%)", "i1p"), ("기관 5일 순매수(%)", "i5p"), ("개인 5일 순매수(%)", "n5p"),
        ("그날 지정 종목 수", "nday"))
P_("# H0425 [단기과열 단일가] 덧조건 다각도 (2026-11-17)\n")
P_("바탕: 학습 %d건 건당 %+.2f%% · 검증 %d건 %+.2f%%. 200만씩 손익(만): 학습 %+.0f · 검증 %+.0f\n" % (L.sum(), X.rD[L].mean(), (~L).sum(), X.rD[~L].mean(), X.rD[L].sum() * 2, X.rD[~L].sum() * 2))
P_("## 1. 재료별 3등분(아래·가운데·위 — 경계는 학습 기간)\n\n| 재료 | 경계 | 학습 아래 | 가운데 | 위 | 위−아래(t) | 검증 아래 | 가운데 | 위 | 위−아래(t) | 판정 |\n|---|---|---|---|---|---|---|---|---|---|---|")
RES = {}
for nm, col in FEAT:
    v = X[col].astype(float); q1, q2 = v[L].quantile([1 / 3, 2 / 3]).values
    if not np.isfinite(q1) or q1 == q2: q1, q2 = v[L].quantile([0.25, 0.75]).values
    b = np.where(v.isna(), -1, np.where(v <= q1, 0, np.where(v <= q2, 1, 2))); cells = []; dif = []
    for _, a, e in PER:
        m = (X.day >= a) & (X.day <= e); mm = [X.rD[m & (b == k)] for k in range(3)]
        lo = X[m & (b == 0)].groupby("day").rD.mean(); hi = X[m & (b == 2)].groupby("day").rD.mean()
        tt = (hi.mean() - lo.mean()) / math.sqrt(hi.var(ddof=1) / len(hi) + lo.var(ddof=1) / len(lo)) if len(hi) > 5 and len(lo) > 5 else 0
        cells.append(" | ".join("%+.2f (%d·%.0f%%)" % (s.mean(), len(s), (s > 0).mean() * 100) if len(s) else "–" for s in mm) + " | %+.2f (t%.1f)" % (mm[2].mean() - mm[0].mean(), tt)); dif.append((mm[2].mean() - mm[0].mean(), tt, mm[1].mean(), mm[0].mean(), mm[2].mean()))
    mono = all(min(d[3], d[4]) - 0.3 <= d[2] <= max(d[3], d[4]) + 0.3 for d in dif)
    ok = (np.sign(dif[0][0]) == np.sign(dif[1][0])) and abs(dif[0][1]) >= 2 and abs(dif[1][1]) >= 1 and mono
    RES[col] = (ok, dif, q1, q2)
    P_("| %s | %.3g · %.3g | %s | %s | %s |" % (nm, q1, q2, cells[0], cells[1], "**통과**(%s 쪽)" % ("위" if dif[0][0] > 0 else "아래") if ok else ("방향만 같음" if np.sign(dif[0][0]) == np.sign(dif[1][0]) and abs(dif[0][1]) >= 1.5 else "–")))
P_("\n## 2. 예·아니오 재료\n\n| 재료 | 학습 예 | 아니오 | 검증 예 | 아니오 |\n|---|---|---|---|---|")
YN = (("1년 안에 또 지정", X.again == 1), ("외국인 5일 순매수 플러스", X.f5 > 0), ("외국인 D 순매수 플러스", X.f1 > 0), ("기관 5일 순매수 플러스", X.i5 > 0), ("외국인·기관 둘 다 5일 플러스", (X.f5 > 0) & (X.i5 > 0)),
      ("5일 안 상한가 있음", X.lim5 >= 1), ("코스닥", X.market == "코스닥"), ("D+1 양봉(종가>시가)", X.c1 > X.o1), ("D+1 종가 < D 종가(눌림)", X.c1 < X.c0), ("사는 날이 목·금(주말 낌)", X.wd.isin([2, 3])), ("사는 날이 월", X.wd == 4))
for nm, m in YN:
    cells = []
    for _, a, e in PER:
        p = (X.day >= a) & (X.day <= e)
        for mm in (m, ~m): s = X.rD[p & mm]; cells.append("%+.2f (%d·%.0f%%)" % (s.mean(), len(s), (s > 0).mean() * 100))
    P_("| %s | %s |" % (nm, " | ".join(cells)))
X.to_pickle("C:/temp/kp/heat_ev4.pkl")
(BASE / "research" / "reports" / "heat4_1117.md").write_text("\n".join(OUT), encoding="utf-8")
