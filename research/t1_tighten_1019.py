# -*- coding: utf-8 -*-
"""[갭 하락 조용주] 후보를 덜 내면서 연 수익은 지키는 조이기 (2026-10-19 사용자 "후보가 좀 덜 나오게 하면서 연수익률은 좋게").

지금 실전 그물(10-13~): 유니버스(거래대금 상위 40%) 아래 1/3 · 어제 거래량 하위 30% · 갭 하위 20% · 시장 대비 -1.5%p 이하(실제 시가) → 시가→종가.
조이기 후보: 시장 대비 문턱(-2·-3·-4) · 갭 순위(10·5%) · 거래량(20·10%) · 5일선 아래 · 하루 위에서 N개만(시장 대비 깊은 순).
연 수익 잣대 둘:
  ① 건당 금액 고정(예: 건당 50만) — 1년 손익 ∝ 연 건수 × 건당 평균 → '연 합계(건당 % 합)'
  ② 하루 예산 고정(그날 후보에 나눠 넣음) — 1년 손익 ∝ 날 바구니 평균의 합 → '연 날 합계(%)'
구간: 옛날 ~15 · 학습 16~22 · 검증 23~ · 비용 0.23 뒤.
    python research/t1_tighten_1019.py
"""
import sys
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "research" / "factory"))
import numpy as np, pandas as pd
import lab, feats as FT


def main():
    H = lab.hist()[["date", "ticker", "oc", "gap", "rgap", "q_gap", "q_vm", "q_d5", "liq"]].copy()
    H["oc"] = H.oc - FT.COST
    base = (H.liq <= 1 / 3) & (H.q_vm <= 0.30) & (H.q_gap <= 0.20) & (H.rgap <= -1.5)
    B = H[base].copy()
    B["per"] = np.where(B.date <= "20151231", "옛날", np.where(B.date <= "20221231", "학습", "검증"))
    yrs = {p: H.loc[H.date.map(lambda d: (d <= "20151231") if p == "옛날" else ("20160101" <= d <= "20221231") if p == "학습" else d >= "20230101"), "date"].nunique() / 250
           for p in ("옛날", "학습", "검증")}

    def row(nm, Z):
        cs = []
        for p in ("옛날", "학습", "검증"):
            q = Z[Z.per == p]
            if len(q) < 30: cs.append("-"); continue
            bk = q.groupby("date").oc.mean()
            cs.append("%.0f건·%+.2f%%·%.0f%% · 연 %+.0f · 날 %+.0f" % (len(q) / yrs[p], q.oc.mean(), (q.oc > 0).mean() * 100, q.oc.sum() / yrs[p], bk.sum() / yrs[p]))
        return "| %s | %s |" % (nm, " | ".join(cs))

    print("칸 = 연 건수 · 건당 평균 · 승률 · 연 합계(건당 금액 고정, %·건) · 연 날 합계(하루 예산 고정, %)\n")
    print("| 판 | 옛날 2005~15 | 학습 2016~22 | 검증 2023~ |"); print("|---|---|---|---|")
    print(row("**지금 그물**(갭 하위20% · 시장 대비 -1.5%p · 거래량 하위30%)", B))
    for thr in (-2, -2.5, -3, -4, -5):
        print(row("시장 대비 %.1f%%p 이하" % thr, B[B.rgap <= thr]))
    for q in (0.10, 0.05):
        print(row("갭 하위 %d%%" % (q * 100), B[B.q_gap <= q]))
    for q in (0.20, 0.10):
        print(row("거래량 하위 %d%%" % (q * 100), B[B.q_vm <= q]))
    print(row("5일선 아래(하위 30%)", B[B.q_d5 <= 0.30]))
    print(row("시장 대비 -3%p · 5일선 아래", B[(B.rgap <= -3) & (B.q_d5 <= 0.30)]))
    print(row("시장 대비 -3%p · 거래량 하위 20%", B[(B.rgap <= -3) & (B.q_vm <= 0.20)]))
    Bs = B.sort_values(["date", "rgap"])
    for n in (3, 5, 10):
        print(row("하루 위에서 %d개만(시장 대비 깊은 순)" % n, Bs.groupby("date").head(n)))
    # 하루 건수 분포
    for nm, Z in (("지금 그물", B), ("시장 대비 -3%p", B[B.rgap <= -3])):
        n = Z.groupby("date").size()
        print("\n%s: 신호 난 날 하루 중앙 %d건 · 90%% 선 %d건 · 최대 %d건" % (nm, n.median(), n.quantile(0.9), n.max()))


if __name__ == "__main__":
    main()
