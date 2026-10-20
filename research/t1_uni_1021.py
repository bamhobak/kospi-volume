# -*- coding: utf-8 -*-
"""[갭 하락 조용주] 종목 크기 문턱 — 유니버스 아래 1/3 대신 2/5 · 3/7 · 4/9 · 1/2 (2026-10-21 사용자).
새 설정(10-21) 위에서: 갭 하위 40% · 어제 거래량 하위 30% · 시장 대비 -1.5%p · 금액 = 기준 50만 × 깊이(1.5~5) × 20일 거래대금 배율(0.3~3).
  ① 손해 없이: 연 건수 · 건당 · 승률 + 1/3 대비 새로 걸린 몫(한계 수익)
  ② 체결 손해 모형(t1_size_liq_1021.fit) 넣고: 1년 손익 · 넣은 돈 대비 · 신호 난 날 평균 투입 — 2016~22 / 2023~ / 2005~15(옛날)
    python research/t1_uni_1021.py
"""
import io, contextlib, sys
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "research")); sys.path.insert(0, str(BASE / "research" / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import t1_size_liq_1021 as SL
import lab, feats as FT

CUTS = [("1/3(지금)", 1 / 3), ("2/5", 2 / 5), ("3/7", 3 / 7), ("4/9", 4 / 9), ("1/2", 1 / 2), ("5/9", 5 / 9), ("2/3", 2 / 3)]
PERS = (("옛날 2005~15", "20050101", "20151231"), ("학습 2016~22", "20160101", "20221231"), ("검증 2023~", "20230101", "20991231"))


def main():
    with contextlib.redirect_stdout(io.StringIO()):
        ab, cf = SL.fit(SL.liq_of_exec())
    impact = lambda p: ab[0] + ab[1] * np.sqrt(p)
    fill = lambda p: 1 / (1 + cf * p)
    H = lab.hist()[["date", "ticker", "oc", "rgap", "q_gap", "q_vm", "liq", "amt20"]].dropna(subset=["oc", "rgap", "q_gap", "liq", "amt20"]).copy()
    H["oc"] = H.oc - FT.COST; H["q_vm"] = H.q_vm.fillna(1.0); H["a20"] = H.amt20 * 1e8
    yrs = {nm: H[(H.date >= lo) & (H.date <= hi)].date.nunique() / 250 for nm, lo, hi in PERS}
    W = H[(H.rgap <= -1.5) & (H.q_gap <= 0.40) & (H.q_vm <= 0.30)]
    base_m = W.liq <= 1 / 3
    print("## ① 손해 없이 (비용 0.23 뒤) — 칸 = 연 건수 · 건당 · 승률\n")
    print("| 크기 문턱 | %s | 1/3 대비 새로 걸린 몫: %s |" % (" | ".join(p[0] for p in PERS), " | ".join(p[0][:2] for p in PERS))); print("|---" * 7 + "|")
    for nm, c in CUTS:
        cells, adds = [], []
        for pn, lo, hi in PERS:
            per = (W.date >= lo) & (W.date <= hi)
            z = W[per & (W.liq <= c)]; a = W[per & (W.liq <= c) & ~base_m]
            cells.append("%.0f · %+.2f%% · %.0f%%" % (len(z) / yrs[pn], z.oc.mean(), (z.oc > 0).mean() * 100))
            adds.append("-" if len(a) < 20 else "%.0f · %+.2f%%" % (len(a) / yrs[pn], a.oc.mean()))
        print("| %s | %s | %s |" % (nm, " | ".join(cells), " | ".join(adds)), flush=True)

    print("\n## ② 체결 손해 넣고 — 기준 50만 × 깊이(1.5~5) × 20일 거래대금 배율(0.3~3)")
    print("칸 = 1년 손익(만원) · 넣은 돈 대비 · 신호 난 날 평균 투입(만원) · 평균 체결\n")
    print("| 크기 문턱 | %s |" % " | ".join(p[0] for p in PERS)); print("|---" * 4 + "|")
    for nm, c in CUTS:
        S = W[W.liq <= c].copy()
        mult = (-S.rgap).clip(1, 5).values
        lm = (S.a20 / S.groupby("date").a20.transform("median")).clip(0.3, 3).values
        amt = 50e4 * mult * lm
        p = amt / S.a20.values * 100
        f = fill(p); pnl = amt * f * (S.oc.values - impact(p)) / 100
        cells = []
        for pn, lo, hi in PERS:
            v = (S.date.values >= lo) & (S.date.values <= hi)
            pd_ = pd.Series((amt * f)[v], index=S.date.values[v]).groupby(level=0).sum().mean() / 1e4
            cells.append("%+.0f · %+.2f%% · %.0f · %.0f%%" % (pnl[v].sum() / yrs[pn] / 1e4, pnl[v].sum() / amt[v].sum() * 100, pd_, np.average(f[v], weights=amt[v]) * 100))
        print("| %s | %s |" % (nm, " | ".join(cells)), flush=True)


if __name__ == "__main__":
    main()
