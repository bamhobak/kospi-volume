# -*- coding: utf-8 -*-
"""[갭 하락 조용주] 싸게 사지는 한도에 금액 맞추기 (2026-10-21 사용자 "기본 50만 기준, 그 배율대로 살 때 최대한 저렴하게 사지는
조건을 최대한 맞춰 주게 조정하면?").
'싸게 사지는 한도' = 우리 금액 ÷ 그 종목 20일 평균 거래대금(참여율 p). 실행 실측: p ≤0.1% 체결 89%·손해 0.62% / 0.1~0.2% 72%·0.99% / 0.2~0.5% 59%·1.27%.
비교(그물 = 10-21 설정: 갭 하위 40% · 거래량 하위 30% · 크기 1/3 · 시장 대비 -1.5):
  A 지금        50만 × 깊이(1.5~5) × 거래대금 배율(0.3~3)
  B 상한        A 금액과 'P × 20일 평균 거래대금' 중 작은 쪽 (P = 0.05·0.1·0.15·0.2%) — 싸게 사지는 한도를 넘는 몫은 안 산다
  C 상한(배율 없이) 50만 × 깊이 와 P × 거래대금 중 작은 쪽
  D 한도까지 채움  P × 거래대금 × (깊이 ÷ 1.5) 를 50만 × 깊이 × 3 이하로 — 거래 많은 종목은 한도까지 더 산다
체결 손해 모형 = t1_size_liq_1021.fit. 칸 = 1년 손익(만원) · 넣은 돈 대비 · 신호 난 날 평균 투입(만원) · 평균 체결.
    python research/t1_pcap_1021.py
"""
import io, contextlib, sys
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "research")); sys.path.insert(0, str(BASE / "research" / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import t1_size_liq_1021 as SL
import lab, feats as FT

PERS = (("옛날 2005~15", "20050101", "20151231"), ("학습 2016~22", "20160101", "20221231"), ("검증 2023~", "20230101", "20991231"))


def main():
    with contextlib.redirect_stdout(io.StringIO()):
        ab, cf = SL.fit(SL.liq_of_exec())
    impact = lambda p: np.maximum(0.0, ab[0] + ab[1] * np.sqrt(p))   # 손해는 0 아래로 안 내려간다
    fill = lambda p: 1 / (1 + cf * p)
    H = lab.hist()[["date", "ticker", "oc", "rgap", "q_gap", "q_vm", "liq", "amt20"]].dropna(subset=["oc", "rgap", "q_gap", "liq", "amt20"]).copy()
    H["oc"] = H.oc - FT.COST; H["q_vm"] = H.q_vm.fillna(1.0); H["a20"] = H.amt20 * 1e8
    yrs = {nm: H[(H.date >= lo) & (H.date <= hi)].date.nunique() / 250 for nm, lo, hi in PERS}
    S = H[(H.rgap <= -1.5) & (H.q_gap <= 0.40) & (H.q_vm <= 0.30) & (H.liq <= 1 / 3)].copy()
    a20 = S.a20.values
    dep = (-S.rgap).clip(1, 5).values
    lm = (S.a20 / S.groupby("date").a20.transform("median")).clip(0.3, 3).values
    A = 50e4 * dep * lm
    print("그물 건수 %d · 2023~ 20일 평균 거래대금 중앙 %.1f억 · A 금액 중앙 %.0f만 → 참여율 중앙 %.3f%%\n" % (
        len(S), np.median(a20[S.date.values >= "20230101"]) / 1e8, np.median(A) / 1e4, np.median(A / a20 * 100)))
    cases = [("A 지금(50만×깊이×거래대금 배율)", A)]
    for P in (0.05, 0.1, 0.15, 0.2):
        cases.append(("B 상한 %.2f%%" % P, np.minimum(A, P / 100 * a20)))
    for P in (0.1, 0.15):
        cases.append(("C 상한 %.2f%%(배율 없이)" % P, np.minimum(50e4 * dep, P / 100 * a20)))
    for P in (0.05, 0.1, 0.15):
        cases.append(("D 한도까지 채움 %.2f%%" % P, np.minimum(P / 100 * a20 * dep / 1.5, 50e4 * dep * 3)))
    print("| 판 | %s |" % " | ".join(p[0] for p in PERS)); print("|---" * 4 + "|")
    for nm, amt in cases:
        p = amt / a20 * 100; f = fill(p); pnl = amt * f * (S.oc.values - impact(p)) / 100
        cells = []
        for pn, lo, hi in PERS:
            v = (S.date.values >= lo) & (S.date.values <= hi)
            pd_ = pd.Series((amt * f)[v], index=S.date.values[v]).groupby(level=0).sum().mean() / 1e4
            cells.append("%+.0f · %+.2f%% · %.0f · %.0f%%" % (pnl[v].sum() / yrs[pn] / 1e4, pnl[v].sum() / amt[v].sum() * 100, pd_, np.average(f[v], weights=amt[v]) * 100))
        print("| %s | %s |" % (nm, " | ".join(cells)), flush=True)
    v = S.date.values >= "20230101"
    print("\n2023~ 종목 금액 분포(만원) — A: 10%% %.0f · 중앙 %.0f · 90%% %.0f / B 0.10%%: 10%% %.0f · 중앙 %.0f · 90%% %.0f" % (
        *np.percentile(A[v] / 1e4, [10, 50, 90]), *np.percentile(np.minimum(A, 0.001 * a20)[v] / 1e4, [10, 50, 90])))


if __name__ == "__main__":
    main()
