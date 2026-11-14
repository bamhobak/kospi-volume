# -*- coding: utf-8 -*-
"""11-15 사용자 "종목당 상한 올리면 체결 손해 더 올라가는 거 아냐?" — 상한별 투입·충격 전 손익·체결 손해(원·%)·충격 뒤 손익."""
import sys
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
def impact(won, a):
    p = np.clip(won / np.where(a > 0, a, np.nan), 0, None)
    return np.nan_to_num(np.maximum(0, -0.25 + 2.40 * np.sqrt(p)), nan=5.0)
Z = pd.read_pickle(r"C:\temp\kp\t6_full_panel_1115.pkl"); Z = Z[Z.half]
Z = Z[(Z.AH50 <= -2.5) & ~((Z.dayr.abs() <= 1.0).fillna(False))].sort_values(["d", "AH50"])
Z["rk"] = Z.groupby("d").cumcount(); Z = Z[Z.rk < 40]
print("| 계좌 | 종목당 상한 | 산 건수 | 총 투입 | 한 건 평균 | 충격 전 손익 | 체결 손해(사기+팔기) | 체결 손해 ÷ 투입 | 충격 뒤 손익 | 충격 뒤 건당 | 하루 평균 계좌 사용 |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for Cap in (5e7, 1e8):
    for cap in (500e4, 1000e4, 1500e4, 3000e4):
        z = Z.copy(); amt = np.minimum(cap, 0.10 * z.v41.values); amt = np.where(amt >= 30e4, amt, 0)
        cum = pd.Series(amt, index=z.index).groupby(z.d.values).cumsum().values
        amt = np.clip(Cap - (cum - amt), 0, amt); amt = np.where(amt >= 30e4, amt, 0); ok = amt > 0; z = z[ok]; amt = amt[ok]
        imp = impact(amt, z.a10.values) + impact(amt, z.v0f.values)
        g = np.sum(amt * z.g_vw.values / 100); c = np.sum(amt * imp / 100); used = pd.Series(amt).groupby(z.d.values).sum()
        print("| %g천만 | %d만 | %d | %.1f억 | %.0f만 | %+.0f만 | %.0f만 | %.2f%% | **%+.0f만** | %+.2f%% | %.0f만 (%.0f%%) |" % (
            Cap / 1e7, cap / 1e4, len(z), amt.sum() / 1e8, amt.mean() / 1e4, g / 1e4, c / 1e4, c / amt.sum() * 100, (g - c) / 1e4, (g - c) / amt.sum() * 100,
            used.mean() / 1e4, used.mean() / Cap * 100))
