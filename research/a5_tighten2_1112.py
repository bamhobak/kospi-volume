# -*- coding: utf-8 -*-
"""[예상 하회] 조이기 2 — a5_tighten_1112.pkl(23일 전 종목-일)로 문턱 판 자세히: 절대 손익·t·앞뒤 구간·상한·거래대금 바닥 (2026-11-12)."""
import io, contextlib, sys, math
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import t1_size_liq_1021 as SL
A = pd.read_pickle(BASE / "data" / "a5_tighten_1112.pkl")
with contextlib.redirect_stdout(io.StringIO()):
    ab, cf = SL.fit(SL.liq_of_exec())
imp = lambda p: np.maximum(0, ab[0] + ab[1] * np.sqrt(p)); fill = lambda p: 1 / (1 + cf * p)
days = sorted(A.date.unique()); nd = len(days)
print("체결 손해 모형 a=%.3f b=%.3f 체결률 c=%.2f" % (ab[0], ab[1], cf))
def row(nm, Z):
    out = [nm, "%.1f" % (len(Z) / nd)]
    for amt in (50e4, 100e4):
        p = amt / Z.a20.fillna(Z.a20.median()) * 100
        net = Z.ret - imp(p); w = amt * fill(p)
        dp = (w * net / 100).groupby(Z.date).sum().reindex(days).fillna(0)
        if amt == 100e4:
            e, l = dp[dp.index < "20261107"], dp[dp.index >= "20261107"]
            tt = dp.mean() / dp.std(ddof=1) * math.sqrt(nd)
            out += ["%+.2f%%" % net.mean(), "%+.1f만 (t %.1f)" % (dp.mean() / 1e4, tt), "%+.1f만" % (e.mean() / 1e4), "%+.1f만" % (l.mean() / 1e4),
                    "%d/%d" % ((dp > 0).sum(), (dp != 0).sum()), "%+.0f만" % (dp.min() / 1e4), "%.0f만" % (amt * Z.groupby("date").size().max() / 1e4)]
        else:
            out += ["%+.1f만" % (dp.mean() / 1e4)]
    print("| " + " | ".join(out) + " |")
print("\n| 판 | 하루 종목 | 50만 하루 | 100만: 충격 뒤 건당 | 하루 손익 | 10-12~11-06 | 11-09~11 | 손익 + 날 | 가장 나쁜 날 | 가장 많은 날 매수 대기 |")
print("|---|---|---|---|---|---|---|---|---|---|")
row("지금: 상위 10%", A[A.q >= 0.9])
for x in (2, 2.5, 3, 3.5, 4): row("a_err ≥ %.1f%%p" % x, A[A.aerr >= x])
for x in (2.5, 3):
    for n in (5, 10, 15):
        row("a_err ≥ %.1f · 하루 최대 %d개(큰 순)" % (x, n), A[A.aerr >= x].sort_values(["date", "aerr"], ascending=[True, False]).groupby("date").head(n))
    for lim in (5e8, 10e8, 20e8):
        row("a_err ≥ %.1f · 거래대금 %d억↑" % (x, lim / 1e8), A[(A.aerr >= x) & (A.a20 >= lim)])
    row("a_err ≥ %.1f · 갭 ≤ -2%%" % x, A[(A.aerr >= x) & (A.gap <= -2)])
    row("a_err ≥ %.1f · 갭 > -2%%" % x, A[(A.aerr >= x) & (A.gap > -2)])
print("\n문턱 판 날짜별(a_err ≥ 3): 날 · 종목 수 · 바구니 평균 · 시장")
Z = A[A.aerr >= 3]
for d in days:
    z = Z[Z.date == d]; m = A[A.date == d].ret.mean()
    print("  %s %3d종목 %+6.2f%% · 시장 %+5.2f%%" % (d, len(z), z.ret.mean() if len(z) else float("nan"), m))
print("\n위 10건 빼면(a_err ≥ 3): 건당 %+.2f%% → %+.2f%%" % (Z.ret.mean(), Z.ret.sort_values().iloc[:-10].mean()))

print("\n하루 예산 고정(종목당 = min(100만, 예산 ÷ 그날 종목 수)) — 매수 대기 금액 상한")
print("| 판 | 하루 예산 | 하루 손익 | 10-12~11-06 | 11-09~11 | 가장 나쁜 날 |")
print("|---|---|---|---|---|---|")
for nm, Z in (("a_err ≥ 3", A[A.aerr >= 3]), ("a_err ≥ 3 · 갭 ≤ -2%", A[(A.aerr >= 3) & (A.gap <= -2)]), ("a_err ≥ 2.5 · 갭 ≤ -2%", A[(A.aerr >= 2.5) & (A.gap <= -2)])):
    for B in (500e4, 1000e4, 2000e4):
        n = Z.groupby("date").t.transform("size"); amt = np.minimum(100e4, B / n)
        p = amt / Z.a20.fillna(Z.a20.median()) * 100
        dp = (amt * fill(p) * (Z.ret - imp(p)) / 100).groupby(Z.date).sum().reindex(days).fillna(0)
        print("| %s | %.0f만 | %+.1f만 | %+.1f만 | %+.1f만 | %+.0f만 |" % (nm, B / 1e4, dp.mean() / 1e4, dp[dp.index < "20261107"].mean() / 1e4, dp[dp.index >= "20261107"].mean() / 1e4, dp.min() / 1e4))
