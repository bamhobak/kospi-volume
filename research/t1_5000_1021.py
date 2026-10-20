# -*- coding: utf-8 -*-
"""[갭 하락 조용주] 계좌 크기 × 기준 금액 — 해마다 1년 손익 (2026-10-21 사용자 "데이 전용으로 5천 정도 배치").
그날 후보를 시장 대비 깊은 순으로 금액(기준 × 깊이 1.5~5 × 20일 거래대금 배율 0.3~3)만큼 담다가 돈이 모자라면 나머지는 못 산다.
체결 손해 모형 = t1_size_liq_1021.fit(실행 실측, 10-21 종가 봉 버그 고친 뒤).
    python research/t1_5000_1021.py
"""
import io, contextlib, sys
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "research")); sys.path.insert(0, str(BASE / "research" / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import t1_size_liq_1021 as SL
import lab, feats as FT


def main():
    with contextlib.redirect_stdout(io.StringIO()):
        ab, cf = SL.fit(SL.liq_of_exec())
    imp = lambda p: np.maximum(0.0, ab[0] + ab[1] * np.sqrt(p)); fill = lambda p: 1 / (1 + cf * p)
    print("손해 모형: 손해 = max(0, %.2f + %.2f×√p) · 체결 = 1/(1 + %.2f×p)\n" % (ab[0], ab[1], cf))
    H = lab.hist()[["date", "oc", "rgap", "q_gap", "q_vm", "liq", "amt20"]].dropna(subset=["oc", "rgap", "q_gap", "liq", "amt20"])
    S0 = H[(H.rgap <= -1.5) & (H.q_gap <= 0.4) & (H.q_vm.fillna(1) <= 0.3) & (H.liq <= 1 / 3)].copy()
    S0["a20"] = S0.amt20 * 1e8; S0["oc"] -= FT.COST
    S0["m"] = (-S0.rgap).clip(1, 5) * (S0.a20 / S0.groupby("date").a20.transform("median")).clip(0.3, 3)
    S0 = S0.sort_values(["date", "rgap"])
    print("| 기준 | 계좌 | 2016~25 평균 | 보통 해(중앙) | 가장 나쁜 해 | 가장 좋은 해 | 2026(10월까지) | 손해 0 평균 | 산 비율 |"); print("|---" * 9 + "|")
    yearly = {}
    for base in (50, 70, 100, 150):
        for acct in (1000, 3000, 5000, None):
            S = S0.copy(); S["amt"] = base * 1e4 * S.m
            p = S.amt / S.a20 * 100; S["pnl"] = S.amt * fill(p) * (S.oc - imp(p)) / 100; S["pnl0"] = S.amt * S.oc / 100
            S["cum"] = S.groupby("date").amt.cumsum()
            K = S if acct is None else S[S.cum <= acct * 1e4]
            K = K[K.date >= "20160101"]; y = K.date.str[:4]
            a = K.groupby(y).pnl.sum() / 1e4; b = K.groupby(y).pnl0.sum() / 1e4
            f = a.loc["2016":"2025"]
            yearly[(base, acct)] = a
            print("| %d만 | %s | %+.0f만 | %+.0f만 | %+.0f만 | %+.0f만 | %+.0f만 | %+.0f만 | %.0f%% |" % (
                base, "무제한" if acct is None else "%d만" % acct, f.mean(), f.median(), f.min(), f.max(), a.get("2026", 0), b.loc["2016":"2025"].mean(),
                len(K) / len(S[S.date >= "20160101"]) * 100), flush=True)
    print("\n## 해마다 — 기준 50만")
    print("| 해 | 1000만 | 3000만 | 5000만 |"); print("|---|---|---|---|")
    for yy in yearly[(50, 1000)].index:
        print("| %s | %s |" % (yy, " | ".join("%+.0f만" % yearly[(50, a)].get(yy, 0) for a in (1000, 3000, 5000))))


if __name__ == "__main__":
    main()
