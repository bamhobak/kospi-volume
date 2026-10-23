# -*- coding: utf-8 -*-
"""[갭 하락 조용주] 시장이 이평선 아래인 날 '더 사면' 실제로 사지나 — 시가에 나온 물량 (2026-10-24 사용자 "아래일 때 더 사는 거, 매물이 별로 없어서 원하는 값에 살 수 있을까?").
그물 = 10-21 확정 본체(4/9 · 갭 하위 40% · 거래량 하위 30% · 시장 대비 -1.5%p) · 2023~ (1분봉이 있는 구간)
시가 물량 = 그날 1분봉 '09:01' 봉(09:00:00~59, 시가 단일가 체결 + 첫 1분) 거래대금. day_exec 는 그 절반을 단일가 몫으로 본다.
지금 금액 = 50만 × 깊이(1.5~5) × 거래대금 배율(0.3~3) — 이걸 시가 물량과 견줘 '내 주문이 시가 물량의 몇 %' 를 이평 위/아래로 나눠 본다.
    python research/day_ma_liq_1024.py
"""
import io, contextlib, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import FinanceDataReader as fdr
import lab, feats as FT
import m1_event as ME


def below(sym, n):
    X = fdr.DataReader(sym, "2021-01-01"); X = X[X.Close > 0]; c = X.Close
    b = (c < c.rolling(n).mean()).shift(1)
    return dict(zip(X.index.strftime("%Y%m%d"), b))


def main():
    H = lab.hist()[["ticker", "date", "oc", "rgap", "q_gap", "q_vm", "liq", "amt20"]].dropna(subset=["oc", "rgap", "q_gap", "liq", "amt20"])
    W = H[(H.rgap <= -1.5) & (H.q_gap <= 0.40) & (H.q_vm.fillna(1) <= 0.30) & (H.liq <= 4 / 9) & (H.date >= "20230101")].copy().reset_index(drop=True)
    W["oc"] -= FT.COST; W["a20"] = W.amt20 * 1e8
    W["amt"] = 50e4 * (-W.rgap).clip(1, 5) * (W.a20 / W.groupby("date").a20.transform("median")).clip(0.3, 3)
    print("그물 %d건 — 1분봉 확인 중" % len(W), flush=True)
    got, miss = ME.ensure("KR", list(zip(W.ticker, W.date)), log=lambda *a: print(*a, flush=True))
    print("새로 받음 %d · 못 받음 %d" % (got, miss), flush=True)
    ov = pd.Series(np.nan, index=W.index); o5 = ov.copy(); op = ov.copy()
    for t, g in W.groupby("ticker"):
        B = ME.bars("KR", t, list(g.date))
        for i, d in zip(g.index, g.date):
            b = B.get(d)
            if b is None or not len(b): continue
            b1 = b[b.hm == "0901"]
            if len(b1): ov[i] = float(b1.v.iloc[0] * b1.o.iloc[0]); op[i] = float(b1.o.iloc[0])
            o5[i] = float((b[b.hm <= "0905"].v * b[b.hm <= "0905"].c).sum())
    W["ov"], W["o5"] = ov, o5
    print("1분봉 시가 봉 있는 것 %d / %d건\n" % (W.ov.notna().sum(), len(W)))
    V = W[W.ov > 0].copy()
    V["ov_a20"] = V.ov / V.a20 * 100                       # 시가 봉 거래대금이 평소 하루 거래대금의 몇 %
    V["part"] = V.amt / (V.ov / 2) * 100                    # 내 주문 ÷ 시가 단일가 몫(09:01 봉 절반)
    print("| 판 | 날 구분 | 건 | 건당 | 시가 봉 거래대금 중앙 | 평소 하루 대비 | 지금 주문 중앙 | 주문 ÷ 시가 몫 중앙 | 90% |")
    print("|---|---|---|---|---|---|---|---|---|")
    for sym, nm in (("KS11", "코스피"), ("KQ11", "코스닥")):
        for n in (20, 60):
            bl = V.date.map(below(sym, n))
            for lab_, m in (("위", bl == False), ("아래", bl == True)):
                z = V[m]
                print("| %s %d일선 | %s | %d | %+.2f%% | %.0f만 | %.1f%% | %.0f만 | %.0f%% | %.0f%% |" % (
                    nm, n, lab_, len(z), z.oc.mean(), z.ov.median() / 1e4, z.ov_a20.median(), z.amt.median() / 1e4, z.part.median(), z.part.quantile(0.9)))
    # 배율을 올리면 주문 ÷ 시가 몫이 어떻게 되나(코스피 20일선 아래 날)
    bl = V.date.map(below("KS11", 20)) == True
    z = V[bl]
    print("\n코스피 20일선 아래 날, 금액을 몇 배로 올리면 — 주문 ÷ 시가 몫(중앙 · 50%%·100%% 넘는 비율)")
    for k in (1, 1.5, 2, 3):
        p = z.part * k
        print("  %.1f배: 중앙 %.0f%% · 50%%↑ %.0f%% · 100%%↑ %.0f%%" % (k, p.median(), (p > 50).mean() * 100, (p > 100).mean() * 100))
    V[["ticker", "date", "oc", "rgap", "a20", "amt", "ov", "o5"]].to_pickle(ROOT.parent / "data" / "day" / "ma_liq_1024.pkl")


if __name__ == "__main__":
    main()
