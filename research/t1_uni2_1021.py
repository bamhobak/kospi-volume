# -*- coding: utf-8 -*-
"""크기 문턱 2차 (2026-10-21 사용자 "1번은 3/8도 비교 · 미장 폭락 과잉 갭도 유니버스 비교 · 근데 1년 수익이 저거밖에 안 돼?").
 A [갭 하락 조용주] 1/3 · 3/8 · 2/5 · 3/7 · 4/9 · 1/2 — 체결 손해 넣은 1년 손익 + **필요한 계좌 크기**(하루 투입 90%·최대) 와
   그 계좌 대비 연 수익률 · 손해 모형을 빼면(실전 1주 기록처럼 밀림이 없다면) 얼마인지
 B [미장 폭락 과잉 갭] 같은 문턱들 — 나스닥 전날 -2.5%↓ · 갭 -2%↓ · 덜 반영(갭 − 짝 미장 예상 갭) 유니버스 하위 10%
    python research/t1_uni2_1021.py
"""
import io, contextlib, sys
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "research")); sys.path.insert(0, str(BASE / "research" / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import FinanceDataReader as fdr
import t1_size_liq_1021 as SL
import lab, feats as FT

CUTS = [("1/3(지금)", 1 / 3), ("3/8", 3 / 8), ("2/5", 2 / 5), ("3/7", 3 / 7), ("4/9", 4 / 9), ("1/2", 1 / 2)]
PERS = (("옛날 2005~15", "20050101", "20151231"), ("학습 2016~22", "20160101", "20221231"), ("검증 2023~", "20230101", "20991231"))


def main():
    with contextlib.redirect_stdout(io.StringIO()):
        ab, cf = SL.fit(SL.liq_of_exec())
    impact = lambda p: ab[0] + ab[1] * np.sqrt(p)
    fill = lambda p: 1 / (1 + cf * p)
    H = lab.hist()[["date", "ticker", "oc", "gap", "rgap", "q_gap", "q_vm", "liq", "amt20", "q_tr_res"]].dropna(subset=["oc", "rgap", "q_gap", "liq", "amt20"]).copy()
    H["oc"] = H.oc - FT.COST; H["q_vm"] = H.q_vm.fillna(1.0); H["a20"] = H.amt20 * 1e8
    yrs = {nm: H[(H.date >= lo) & (H.date <= hi)].date.nunique() / 250 for nm, lo, hi in PERS}

    W = H[(H.rgap <= -1.5) & (H.q_gap <= 0.40) & (H.q_vm <= 0.30)]
    print("## A. [갭 하락 조용주] — 기준 50만 × 깊이(1.5~5) × 거래대금 배율(0.3~3), 체결 손해 넣음")
    print("칸 = 1년 손익(만원) · 하루 투입 중앙/90%/최대(만원, 신호 난 날) · **계좌 = 하루 투입 90% 선**일 때 연 수익률 · (손해 0 이라면 1년 손익)\n")
    print("| 크기 문턱 | %s |" % " | ".join(p[0] for p in PERS)); print("|---" * 4 + "|")
    for nm, c in CUTS:
        S = W[W.liq <= c]
        mult = (-S.rgap).clip(1, 5).values
        lm = (S.a20 / S.groupby("date").a20.transform("median")).clip(0.3, 3).values
        amt = 50e4 * mult * lm; p = amt / S.a20.values * 100; f = fill(p)
        pnl = amt * f * (S.oc.values - impact(p)) / 100
        pnl0 = amt * S.oc.values / 100
        cells = []
        for pn, lo, hi in PERS:
            v = (S.date.values >= lo) & (S.date.values <= hi)
            d = pd.Series(amt[v], index=S.date.values[v]).groupby(level=0).sum() / 1e4
            yp = pnl[v].sum() / yrs[pn] / 1e4
            cells.append("%+.0f · %.0f/%.0f/%.0f · 연 %+.0f%% · (%+.0f)" % (yp, d.median(), d.quantile(0.9), d.max(), yp / d.quantile(0.9) * 100, pnl0[v].sum() / yrs[pn] / 1e4))
        print("| %s | %s |" % (nm, " | ".join(cells)), flush=True)

    # B. T4
    X = fdr.DataReader("IXIC", "2005-01-01"); X = X[X.Close > 0]
    us = X.Close.pct_change() * 100; us.index = us.index.strftime("%Y%m%d"); ud = us.index.values
    H["us"] = H.date.map({d: (us.iloc[np.searchsorted(ud, d) - 1] if np.searchsorted(ud, d) > 0 else np.nan) for d in H.date.unique()})
    T = H[(H.us <= -2.5) & (H.gap <= -2.0) & (H.q_tr_res <= 0.10)].copy()
    print("\n## B. [미장 폭락 과잉 갭] — 손해 없이(비용 0.23 뒤) · 칸 = 연 날 수 · 연 건수 · 건당 · 승률 · 날 바구니 평균")
    print("(덜 반영 순위 자료가 있는 날만: 첫날 %s)\n" % (T.date.min() if len(T) else "-"))
    print("| 크기 문턱 | %s | 1/3 대비 새로 걸린 몫(학습·검증) | 손해 넣은 1년 손익(50만 균등, 학습·검증) |" % " | ".join(p[0] for p in PERS)); print("|---" * 6 + "|")
    T0 = T.liq <= 1 / 3
    for nm, c in CUTS + [("2/3", 2 / 3), ("전부", 1.01)]:
        Z = T[T.liq <= c]; cells = []
        for pn, lo, hi in PERS:
            z = Z[(Z.date >= lo) & (Z.date <= hi)]
            if len(z) < 20: cells.append("-"); continue
            cells.append("%.1f일 · %.0f건 · %+.2f%% · %.0f%% · 날 %+.2f%%" % (z.date.nunique() / yrs[pn], len(z) / yrs[pn], z.oc.mean(), (z.oc > 0).mean() * 100, z.groupby("date").oc.mean().mean()))
        add = []
        for pn, lo, hi in PERS[1:]:
            a = T[(T.liq <= c) & ~T0 & (T.date >= lo) & (T.date <= hi)]
            add.append("-" if len(a) < 10 else "%.0f건 %+.2f%%" % (len(a) / yrs[pn], a.oc.mean()))
        im = []
        for pn, lo, hi in PERS[1:]:
            z = Z[(Z.date >= lo) & (Z.date <= hi)]
            p = 50e4 / z.a20.values * 100
            im.append("%+.0f" % ((50e4 * fill(p) * (z.oc.values - impact(p)) / 100).sum() / yrs[pn] / 1e4))
        print("| %s | %s | %s | %s |" % (nm, " | ".join(cells), " / ".join(add), " / ".join(im)), flush=True)


if __name__ == "__main__":
    main()
