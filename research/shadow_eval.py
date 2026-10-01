# -*- coding: utf-8 -*-
"""그림자 규칙 일괄 판정 — data/shadow/log.csv(shadow.py 가 매일 적은 신호)의 실제 성적 (2026-10-02 · 1년쯤 뒤에 돌린다).
신호일 다음날 시가 매수 · 규칙 보유일 뒤 종가 · 비용 차감(kr_scan 의 cost) — 보유가 안 끝난 신호는 '진행 중'으로 따로 센다.
같은 날 유니버스(거래대금 상위 40%) 중앙 대비 초과도 같이 본다.
    python research/shadow_eval.py
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.stdout.reconfigure(encoding="utf-8")
L = pd.read_csv(BASE / "data" / "shadow" / "log.csv", dtype={"ticker": str, "date": str})
K = pd.read_pickle(BASE / "data" / "kr_scan.pkl")[["ticker", "date", "close", "buy", "cost", "amt20"]].sort_values(["ticker", "date"])
g = K.groupby("ticker", sort=False).close
q = K.groupby("date").amt20.rank(pct=True) >= 0.6
out = []
for rule, z in L.groupby("rule"):
    h = int(z.hold.iloc[0])
    K["f"] = (g.shift(-h) / K.buy - 1) * 100 - K.cost
    b = K[q].groupby("date").f.median()
    m = z.merge(K[["ticker", "date", "f"]], on=["ticker", "date"], how="left")
    m["ex"] = m.f - m.date.map(b)
    d = m.dropna(subset=["f"])
    out.append((rule, len(z), len(d), d.f.mean() if len(d) else np.nan, d.f.median() if len(d) else np.nan,
                (d.f > 0).mean() * 100 if len(d) else np.nan, d.ex.median() if len(d) else np.nan, h))
print("| 규칙 | 기록 | 끝난 것 | 평균 | 중앙 | 승률 | 같은 날 대비 초과 중앙 | 보유 |"); print("|---|---|---|---|---|---|---|---|")
for r in out:
    print("| %s | %d | %d | %+.2f | %+.2f | %.0f%% | %+.2f | %d일 |" % r)
