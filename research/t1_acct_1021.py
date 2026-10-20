# -*- coding: utf-8 -*-
"""[갭 하락 조용주] 크기 문턱 1/3 vs 3/7 — 같은 계좌(투자금)일 때 1년 손익 (2026-10-21 사용자 "3/7일 때랑 투자금 비교").
계좌 돈 = 그날 쓸 수 있는 돈(데이라 매일 같은 돈이 돈다). 그날 후보를 시장 대비 깊은 순으로 금액(50만 × 깊이 × 거래대금 배율)만큼
담다가 돈이 모자라면 나머지는 못 산다(실전 주문 순서와 같다). 체결 손해 모형 = t1_size_liq_1021.fit.
⚠ 실전에선 안 사진 지정가 주문도 09:01 취소 전까지 돈을 잡아 둔다 — 여기선 사진 것만 돈을 쓰므로 작은 계좌는 실제보다 후하다.
    python research/t1_acct_1021.py
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
ACCTS = [300, 500, 700, 1000, 1500, 2000, 3000, 5000, None]     # 만원 · None = 무제한


def main():
    with contextlib.redirect_stdout(io.StringIO()):
        ab, cf = SL.fit(SL.liq_of_exec())
    impact = lambda p: np.maximum(0.0, ab[0] + ab[1] * np.sqrt(p))   # 손해는 0 아래로 안 내려간다
    fill = lambda p: 1 / (1 + cf * p)
    H = lab.hist()[["date", "ticker", "oc", "rgap", "q_gap", "q_vm", "liq", "amt20"]].dropna(subset=["oc", "rgap", "q_gap", "liq", "amt20"]).copy()
    H["oc"] = H.oc - FT.COST; H["q_vm"] = H.q_vm.fillna(1.0); H["a20"] = H.amt20 * 1e8
    yrs = {nm: H[(H.date >= lo) & (H.date <= hi)].date.nunique() / 250 for nm, lo, hi in PERS}
    W = H[(H.rgap <= -1.5) & (H.q_gap <= 0.40) & (H.q_vm <= 0.30)]
    R = {}
    for nm, c in (("1/3", 1 / 3), ("3/7", 3 / 7), ("4/9", 4 / 9)):
        S = W[W.liq <= c].copy()
        S["amt"] = 50e4 * (-S.rgap).clip(1, 5) * (S.a20 / S.groupby("date").a20.transform("median")).clip(0.3, 3)
        p = S.amt / S.a20 * 100
        S["pnl"] = S.amt * fill(p) * (S.oc - impact(p)) / 100
        S = S.sort_values(["date", "rgap"])
        S["cum"] = S.groupby("date").amt.cumsum()
        S["tot"] = S.groupby("date").amt.transform("sum")
        R[nm] = S
    print("칸 = 1년 손익(만원) · 계좌 대비 연 수익률 · 산 건수 비율(후보 중)\n")
    print("| 계좌(투자금) | 문턱 | %s |" % " | ".join(p[0] for p in PERS)); print("|---" * 5 + "|")
    for A in ACCTS:
        for nm in ("1/3", "3/7", "4/9"):
            S = R[nm]
            k = S if A is None else S[S.cum <= A * 1e4]
            cells = []
            for pn, lo, hi in PERS:
                v = (k.date >= lo) & (k.date <= hi); vall = (S.date >= lo) & (S.date <= hi)
                yp = k.pnl[v].sum() / yrs[pn] / 1e4
                cells.append("%+.0f · %s · %.0f%%" % (yp, ("%+.0f%%" % (yp / A * 100)) if A else "-", v.sum() / vall.sum() * 100))
            print("| %s | %s | %s |" % ("무제한" if A is None else "%d만" % A, nm, " | ".join(cells)), flush=True)
    # 둘째 방식: 돈이 모자란 날은 모든 종목 금액을 같은 비율로 줄여 전부 산다
    print("\n## 돈 모자란 날 금액을 같은 비율로 줄여 전부 사기\n")
    print("| 계좌(투자금) | 문턱 | %s |" % " | ".join(p[0] for p in PERS)); print("|---" * 5 + "|")
    for A in ACCTS[:-1]:
        for nm in ("1/3", "3/7", "4/9"):
            S = R[nm]
            sc = np.minimum(1.0, A * 1e4 / S.tot.values)
            amt = S.amt.values * sc; pp = amt / S.a20.values * 100
            pnl = amt * fill(pp) * (S.oc.values - impact(pp)) / 100
            cells = []
            for pn, lo, hi in PERS:
                v = (S.date.values >= lo) & (S.date.values <= hi)
                yp = pnl[v].sum() / yrs[pn] / 1e4
                cells.append("%+.0f · %+.0f%%" % (yp, yp / A * 100))
            print("| %d만 | %s | %s |" % (A, nm, " | ".join(cells)), flush=True)


if __name__ == "__main__":
    main()
