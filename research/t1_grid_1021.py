# -*- coding: utf-8 -*-
"""[갭 하락 조용주] 기준 금액 × 깊이 배율 상한 × 그물 넓이 — 체결 손해 모형을 넣고 1년 손익 (2026-10-21, t1_loosen·t1_size_liq 이어서).
손해·체결 모형 = t1_size_liq_1021.fit(실행 실측) · 금액 = 기준 × min(시장 대비 깊이, 상한) × (20일 거래대금 ÷ 그날 후보 중앙)^a(0.3~3배, 같은 돈 합).
    python research/t1_grid_1021.py
"""
import sys
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "research")); sys.path.insert(0, str(BASE / "research" / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import t1_size_liq_1021 as SL
import lab, feats as FT


def main():
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        ab, cf = SL.fit(SL.liq_of_exec())
    impact = lambda p: ab[0] + ab[1] * np.sqrt(p)
    fill = lambda p: 1 / (1 + cf * p)
    H = lab.hist()[["date", "ticker", "oc", "rgap", "q_gap", "q_vm", "liq", "amt20"]].dropna(subset=["oc", "rgap", "q_gap", "liq", "amt20"])
    H = H[H.date >= "20160101"].copy()
    H["oc"] = H.oc - FT.COST; H["q_vm"] = H.q_vm.fillna(1.0); H["a20"] = H.amt20 * 1e8
    nd = H.date.nunique() / 250; nd2 = H[H.date >= "20230101"].date.nunique() / 250
    NETS = [("지금(-1.5·갭20·거래량30·1/3)", -1.5, 0.2, 0.3, 1 / 3), ("갭 40%", -1.5, 0.4, 0.3, 1 / 3),
            ("거래량 50%", -1.5, 0.2, 0.5, 1 / 3), ("크기 1/2", -1.5, 0.2, 0.3, 0.5), ("시장 대비 -1.0", -1.0, 0.2, 0.3, 1 / 3),
            ("거래량 50%·크기 1/2", -1.5, 0.2, 0.5, 0.5)]
    print("칸 = 1년 손익(만원, 2016~) · 2023~ 1년 · 넣은 돈 대비 · 하루 평균 넣는 돈(신호 난 날, 만원)\n")
    for a in (0.0, 1.0):
        print("## 크기 배율 %s" % ("없음" if a == 0 else "20일 거래대금^%.1f" % a))
        print("| 그물 | 기준 | 상한 1배 | 상한 2배 | 상한 3배 | 상한 5배(지금) |"); print("|---|---|---|---|---|---|")
        for nm, rg, qg, qv, lq in NETS:
            S = H[(H.rgap <= rg) & (H.q_gap <= qg) & (H.q_vm <= qv) & (H.liq <= lq)].copy()
            rel = (S.a20 / S.groupby("date").a20.transform("median")) ** a
            for base in (20, 30, 50, 70, 100):
                cells = []
                for cap in (1, 2, 3, 5):
                    mult = (-S.rgap).clip(1, cap).values
                    m = rel.clip(0.3, 3).values; m = m * mult.sum() / (mult * m).sum()
                    amt = base * 1e4 * mult * m
                    p = amt / S.a20.values * 100
                    pnl = amt * fill(p) * (S.oc.values - impact(p)) / 100
                    v = S.date.values >= "20230101"
                    perday = pd.Series(amt * fill(p), index=S.date.values).groupby(level=0).sum().mean() / 1e4
                    cells.append("%+.0f · %+.0f · %+.2f%% · %.0f" % (pnl.sum() / nd / 1e4, pnl[v].sum() / nd2 / 1e4, pnl.sum() / amt.sum() * 100, perday))
                print("| %s | %d만 | %s |" % (nm, base, " | ".join(cells)), flush=True)
        print()


if __name__ == "__main__":
    main()
