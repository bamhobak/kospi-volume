# -*- coding: utf-8 -*-
"""[갭 하락 조용주] 이동평균선 아래면 안 하기 — 20·40·60일선 (2026-10-24 사용자 "데이 규칙 20일선 아래나 40일 60일선 아래일 때 거래 안 하는 거 실측").
'아래'를 두 가지로 본다(둘 다 장 시작 전에 아는 값 = 어제 종가 기준):
  ① 시장 — 코스피·코스닥 지수 어제 종가가 그 지수 N일선 아래인 날은 쉰다(코스피만 · 코스닥만 · 둘 중 하나라도)
  ② 종목 — 그 후보의 어제 종가가 자기 N일선 아래면 그 종목만 안 산다
그물 = 10-21 확정(유니버스 아래 4/9 · 갭 하위 40% · 어제 거래량 하위 30% · 실제 시장 대비 -1.5%p) · 시가→종가 · 비용 0.23 뒤 · 밀림 전.
잣대: 남는 거래의 연 건수·건당·승률·날 바구니(같은 날 몰림 보정)·연 합계 + **빼 버린 몫의 건당**(플러스면 빼서 손해).
    python research/day_ma_1024.py
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import FinanceDataReader as fdr
import lab, feats as FT, common as C

PERS = (("옛날 2005~15", "20050101", "20151231"), ("학습 2016~22", "20160101", "20221231"), ("검증 2023~", "20230101", "20991231"))
MAS = (20, 40, 60)


def index_below(sym):
    X = fdr.DataReader(sym, "2004-01-01"); X = X[X.Close > 0]
    c = X.Close
    out = {}
    for n in MAS:
        below = (c < c.rolling(n).mean()).shift(1)                       # 어제 종가가 어제까지의 N일선 아래 → 오늘 쉰다
        out[n] = dict(zip(X.index.strftime("%Y%m%d"), below))
    return out


def main():
    H = lab.hist()[["ticker", "date", "oc", "rgap", "q_gap", "q_vm", "liq"]].dropna(subset=["oc", "rgap", "q_gap", "liq"])
    W = H[(H.rgap <= -1.5) & (H.q_gap <= 0.40) & (H.q_vm.fillna(1) <= 0.30) & (H.liq <= 4 / 9)].copy()
    W["oc"] -= FT.COST
    yrs = {nm: H[(H.date >= lo) & (H.date <= hi)].date.nunique() / 250 for nm, lo, hi in PERS}
    # 종목 자기 N일선(어제 종가 기준)
    P = pd.read_pickle(C.CACHE / "factory_px.pkl")[["ticker", "date", "close"]].sort_values(["ticker", "date"])
    g = P.groupby("ticker", sort=False).close
    for n in MAS:
        P["sb%d" % n] = (P.close < g.transform(lambda s: s.rolling(n).mean())).groupby(P.ticker).shift(1)
    W = W.merge(P[["ticker", "date"] + ["sb%d" % n for n in MAS]], on=["ticker", "date"], how="left")
    KP, KQ = index_below("KS11"), index_below("KQ11")
    for n in MAS:
        W["kp%d" % n] = W.date.map(KP[n]); W["kq%d" % n] = W.date.map(KQ[n])
    print("그물 %d건 · 지수 자료 %s~ · 종목 이평 자료 %s 까지\n" % (len(W), min(KP[20]), P.date.max()))

    def cells(Z, drop):
        out = []
        for pn, lo, hi in PERS:
            z = Z[(Z.date >= lo) & (Z.date <= hi)]; k = z[~drop.loc[z.index]]; x = z[drop.loc[z.index]]
            if len(z) < 30: out.append("-"); continue
            out.append("%.0f건 · %+.2f%% · %.0f%% · 날 %+.2f%% · 연 %+.0f | 뺀 몫 %.0f건 %s" % (
                len(k) / yrs[pn], k.oc.mean(), (k.oc > 0).mean() * 100, k.groupby("date").oc.mean().mean() if len(k) else np.nan,
                k.oc.sum() / yrs[pn], len(x) / yrs[pn], ("%+.2f%%" % x.oc.mean()) if len(x) >= 10 else "-"))
        return out

    T = lambda s: s.fillna(False).astype(bool)
    rows = [("지금(다 함)", pd.Series(False, index=W.index))]
    for n in MAS:
        rows.append(("코스피 %d일선 아래면 쉼" % n, T(W["kp%d" % n])))
    for n in MAS:
        rows.append(("코스닥 %d일선 아래면 쉼" % n, T(W["kq%d" % n])))
    for n in MAS:
        rows.append(("코스피·코스닥 하나라도 %d일선 아래면 쉼" % n, T(W["kp%d" % n]) | T(W["kq%d" % n])))
    for n in MAS:
        rows.append(("종목이 자기 %d일선 아래면 안 삼" % n, T(W["sb%d" % n])))
    print("칸 = (남은 거래) 연 건수 · 건당 · 승률 · 날 바구니 · 연 합계(건당 %%의 1년 합) | 뺀 몫 연 건수·건당 (비용 0.23 뒤, 밀림 전)\n")
    print("| 판 | %s |" % " | ".join(p[0] for p in PERS)); print("|---" * 4 + "|")
    for nm, d in rows:
        print("| %s | %s |" % (nm, " | ".join(cells(W, d))), flush=True)
    # 종목 이평 아래 비율(참고)
    print("\n참고: 후보가 자기 20·40·60일선 아래인 비율 %.0f%% · %.0f%% · %.0f%%" % tuple(T(W["sb%d" % n]).mean() * 100 for n in MAS))


if __name__ == "__main__":
    main()
