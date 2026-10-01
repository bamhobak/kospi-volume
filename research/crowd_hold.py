# -*- coding: utf-8 -*-
"""우리 신호가 몰리는 날 = 투매의 날 → 그날 산 신호는 길게 들고 가면 나은가 (2026-10-02 사용자 제안 7번).

국내 9규칙 신호(rule_scan.kr_signals, 자리 제한 없음 = 전부 산다) · 그날 전 규칙 신호 수 = '몰림'.
몰림 상위 10%·20% 날 vs 나머지 날 — 규칙 원래 청산(r) / 고정 보유 20·60·120·250일(다음날 시가 매수 · 비용 차감) 평균·중앙·승률.
'몰린 날에는 보유를 늘려라' 가 맞으려면: 몰린 날의 n120(또는 n250) − r 가 나머지 날보다 확실히 커야 하고 학습·검증 둘 다.

    python research/crowd_hold.py
"""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
import rule_scan as RS
S = RS.kr_signals()[["date", "ticker", "rid", "r"]]
sys.stdout = sys.__stdout__; sys.stdout.reconfigure(encoding="utf-8")
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
K = pd.read_pickle(BASE / "data" / "kr_scan.pkl")[["ticker", "date", "close", "buy", "cost"]].sort_values(["ticker", "date"])
g = K.groupby("ticker", sort=False).close
for h in (20, 60, 120, 250):
    K["n%d" % h] = (g.shift(-h) / K.buy - 1) * 100 - K.cost
S = S.merge(K[["ticker", "date", "n20", "n60", "n120", "n250"]], on=["ticker", "date"], how="left")
S["crowd"] = S.groupby("date").ticker.transform("size")
S["per"] = np.where(S.date <= "20151231", "옛날", np.where(S.date <= "20221231", "학습", "검증"))
q90 = S.drop_duplicates("date").crowd.quantile(0.9); q80 = S.drop_duplicates("date").crowd.quantile(0.8)
S["grp"] = np.where(S.crowd >= q90, "몰린 날 상위10%", np.where(S.crowd >= q80, "상위10~20%", "나머지 날"))
P("# 신호 몰린 날 = 투매일 → 길게 들고 가기 · %s" % time.strftime("%Y-%m-%d")); P("")
P("국내 규칙 신호 %s건 · 그날 신호 수 상위 10%% 문턱 %d개 · 20%% 문턱 %d개 (신호가 난 날 기준)" % (f"{len(S):,}", q90, q80)); P("")
P("| 구간 | 묶음 | 신호 | 원래 청산 평균·중앙 | 20일 | 60일 | 120일 | 250일 | 250일 승률 |"); P("|---|---|---|---|---|---|---|---|---|")
for per in ("옛날", "학습", "검증"):
    for grp in ("몰린 날 상위10%", "상위10~20%", "나머지 날"):
        z = S[(S.per == per) & (S.grp == grp)]
        if len(z) < 20:
            continue
        f = lambda c: "%+.1f / %+.1f" % (z[c].mean(), z[c].median()) if z[c].notna().sum() >= 20 else "-"
        P("| %s | %s | %d | %s | %s | %s | %s | %s | %s |" % (per, grp, len(z), f("r"), f("n20"), f("n60"), f("n120"), f("n250"),
                                                        "%.0f%%" % ((z.n250 > 0).mean() * 100) if z.n250.notna().sum() >= 20 else "-"))
P(""); P("칸 = 평균 / 중앙(%, 비용 차감). '원래 청산'은 portfolio.py 규칙대로(트레일링·손절·보유일).")
P(""); P("## 몰린 날 신호가 어느 해에 있었나"); P("")
z = S[S.grp == "몰린 날 상위10%"]
P(", ".join("%s %d건" % kv for kv in z.date.str[:4].value_counts().sort_index().items()))
(ROOT / "reports" / ("crowd_hold_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")
