# -*- coding: utf-8 -*-
"""2026-11-13 사용자 "응" — [장후 낙폭](T6) 하루 계좌 한도 3천만 실측.
① 몰리는 날 한도 밖(깊은 순으로 쌓아 3천만 넘는 뒤쪽) 몫이 평소에도 좋은가 — 순번 구간별 건당(충격 뒤)·해별
② 종목당 500만·k0.10 고정, 계좌 한도만 3천만·5천만·8천만·1억·무제한 → T6 혼자 손익(달·해·최악의 날·묶이는 돈)
모형 = research/day_acct_1e8_1110(A.load·A.nimp: VWAP 매수 g_vw · 매수 충격 a10 · 매도 충격 v0f) 그대로, 2025-04~2026-10-08.
    python research/t6_cap_1113.py
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import day_acct_1e8_1110 as A
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
C6, K6 = 500e4, 0.10
T6, _, _ = A.load()
rows = []
for d, g in T6.groupby("d1"):
    g = g.head(40)
    amt = np.minimum(C6, K6 * g.v41.to_numpy()); amt = np.where(amt >= 30e4, amt, 0)
    before = np.cumsum(amt) - amt                                  # 내 앞에 쌓인 돈(깊은 순)
    r = g.g_vw.to_numpy() - A.nimp(amt, g.a10.to_numpy()) - A.nimp(amt, g.v0f.to_numpy())
    for i in range(len(g)):
        if amt[i] <= 0: continue
        rows.append(dict(d=d, y=d[:4], before=before[i], amt=amt[i], r=r[i], raw=g.g_vw.iloc[i], ah=g.AH50.iloc[i], dayn=int((amt > 0).sum()), daytot=amt.sum()))
X = pd.DataFrame(rows)
P("# [장후 낙폭] 하루 계좌 한도 · %s~%s · %d일 · %d건 (종목당 min(500만, 10분 대금×0.10), 30만↓ 안 삼, 충격 뒤)" % (A.D0, A.D1, X.d.nunique(), len(X)))
P("\n## ① 깊은 순으로 쌓았을 때 몇 번째 돈 구간이냐 — 건당 수익\n")
P("| 앞에 쌓인 돈 | 건수 | 날 수 | 건당(충격 뒤) | 승률 | 2025 | 2026 | t |")
P("|---|---|---|---|---|---|---|---|")
bins = [(0, 3e7, "0~3천만(지금 삼)"), (3e7, 5e7, "3천만~5천만"), (5e7, 8e7, "5천만~8천만"), (8e7, 1e8, "8천만~1억"), (1e8, 1e12, "1억↑")]
for lo, hi, nm in bins:
    z = X[(X.before >= lo) & (X.before < hi)]
    if not len(z): continue
    t = z.r.mean() / (z.r.std(ddof=1) / np.sqrt(len(z))) if len(z) > 2 else np.nan
    yy = {y: z[z.y == y].r.mean() for y in ("2025", "2026")}
    P("| %s | %d | %d | %+.2f%% | %.0f%% | %s | %s | %.1f |" % (nm, len(z), z.d.nunique(), z.r.mean(), (z.r > 0).mean() * 100,
      "%+.2f%%" % yy["2025"] if yy["2025"] == yy["2025"] else "-", "%+.2f%%" % yy["2026"] if yy["2026"] == yy["2026"] else "-", t))
# 몰리는 날만: 그날 쌓인 돈이 3천만 넘는 날 — 안쪽 vs 바깥쪽 (같은 날끼리)
busy = X[X.daytot > 3e7]
ins, outs = busy[busy.before < 3e7], busy[busy.before >= 3e7]
P("\n몰리는 날(그날 살 돈 합 3천만↑) %d일 — 안쪽 %d건 %+.2f%% · 한도 밖 %d건 %+.2f%% · 한도 밖이 플러스인 날 %.0f%%" % (
    busy.d.nunique(), len(ins), ins.r.mean(), len(outs), outs.r.mean(), (outs.groupby("d").r.mean() > 0).mean() * 100))
dd = busy.groupby("d").apply(lambda g: pd.Series(dict(i=g[g.before < 3e7].r.mean(), o=g[g.before >= 3e7].r.mean(), n=len(g)))).dropna()
P("같은 날 짝(바깥 − 안쪽) 평균 %+.2f%%p · 바깥이 나은 날 %.0f%% (%d일)" % ((dd.o - dd.i).mean(), ((dd.o - dd.i) > 0).mean() * 100, len(dd)))
P("\n몰리는 날 목록(위 15일, 살 돈 합 큰 순):")
for d, g in sorted(busy.groupby("d"), key=lambda kv: -kv[1].daytot.iloc[0])[:15]:
    P("  %s 종목 %d · 합 %.0f만 · 안쪽 %+.2f%% · 바깥 %+.2f%%" % (d, len(g), g.daytot.iloc[0] / 1e4, g[g.before < 3e7].r.mean(), g[g.before >= 3e7].r.mean()))

P("\n## ② 계좌 한도만 바꿔서 — T6 혼자 (종목당 500만·k0.10)\n")
P("| 하루 한도 | 달 평균 | 달 중앙 | 최악의 달 | 최악의 날 | 2025 달 평균 | 2026 달 평균 | 한도 걸린 날 | 묶이는 돈 평균 / 최대 | 넣은 돈 대비 |")
P("|---|---|---|---|---|---|---|---|---|---|")
for cap in (3e7, 5e7, 8e7, 1e8, 1e12):
    a = np.clip(cap - X.before, 0, X.amt); a = np.where(a >= 30e4, a, 0)
    Y = X.assign(a=a, pnl=a * X.r / 100)
    D = Y.groupby("d").agg(pnl=("pnl", "sum"), use=("a", "sum"))
    M = D.pnl.groupby(D.index.str[:6]).sum()
    MY = M.groupby(M.index.str[:4]).mean()
    hit = (X.groupby("d").daytot.first() > cap).mean() * 100
    P("| %s | %+.0f만 | %+.0f만 | %+.0f만 | %+.0f만 | %+.0f만 | %+.0f만 | %.0f%% | %.0f / %.0f만 | %+.2f%% |" % (
        "무제한" if cap > 1e11 else ("%g억" % (cap / 1e8) if cap >= 1e8 else "%g천만" % (cap / 1e7)), M.mean() / 1e4, M.median() / 1e4, M.min() / 1e4,
        D.pnl.min() / 1e4, MY.get("2025", np.nan) / 1e4, MY.get("2026", np.nan) / 1e4, hit, D.use.mean() / 1e4, D.use.max() / 1e4, Y.pnl.sum() / Y.a.sum() * 100))
(ROOT / "reports" / "t6_cap_1113.md").write_text("\n".join(OUT), encoding="utf-8")
