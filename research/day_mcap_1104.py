# -*- coding: utf-8 -*-
"""[갭 하락 조용주] 시가총액 작은 종목 안 사기 (2026-11-04 사용자 "관리종목 중 시총 100억·150억 미만은 안 사는 조건 · 관리종목 아니어도 너무 작은 시총 안 사기").
시총 = 어제 종가 기준(억원, 패널 mcap). 관리종목 표시는 day_admin_1104.py 결과(data/day/admin_1104.pkl).
잣대: 뺀 몫의 건당·승률·중앙(플러스면 빼서 손해) · 남은 쪽 연 합계(건당 %의 1년 합) · 최악 5건.
    python research/day_mcap_1104.py
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd
import lab

PERS = (("옛날 2010~15", "20100101", "20151231"), ("학습 2016~22", "20160101", "20221231"), ("검증 2023~", "20230101", "20991231"))


def main():
    H = lab.hist()[["ticker", "date", "mcap"]]
    yrs = {nm: H[(H.date >= lo) & (H.date <= hi)].date.nunique() / 250 for nm, lo, hi in PERS}
    W = pd.read_pickle(BASE / "data" / "day" / "admin_1104.pkl").merge(H, on=["ticker", "date"], how="left")
    print("거래 %d건 · 시총 없음 %d건 · 시총 중앙 %.0f억 · 10%% %.0f억 · 관리종목 %d건\n" % (len(W), W.mcap.isna().sum(), W.mcap.median(), W.mcap.quantile(0.1), W.adm.sum()))
    cell = lambda z: "%d건 %+.2f%% · 승 %.0f%% · 중앙 %+.2f" % (len(z), z.oc.mean(), (z.oc > 0).mean() * 100, z.oc.median()) if len(z) >= 5 else "%d건" % len(z)

    def table(title, rows):
        print("### " + title + "\n")
        print("| 조건 | %s | 연 합계 변화(검증) |" % " | ".join("%s 뺀 몫" % p[0] for p in PERS)); print("|---" * 5 + "|")
        for nm, drop in rows:
            cs = []
            for pn, lo, hi in PERS:
                z = W[(W.date >= lo) & (W.date <= hi)]; cs.append(cell(z[drop.loc[z.index]]))
            z = W[W.date >= "20230101"]; x = z[drop.loc[z.index]]
            print("| %s | %s | %+.0f (지금 %+.0f) |" % (nm, " | ".join(cs), -x.oc.sum() / yrs["검증 2023~"], z.oc.sum() / yrs["검증 2023~"]))
        print()

    adm, mc = W.adm.astype(bool), W.mcap
    table("관리종목 중 작은 것만 빼기", [("관리종목 & 시총 %d억 미만" % k, adm & (mc < k)) for k in (100, 150, 200, 300)] + [("관리종목 전부", adm)])
    table("관리종목 무관 — 시총 작은 것 빼기", [("시총 %d억 미만" % k, mc < k) for k in (100, 150, 200, 300, 500)])
    print("시총 구간별 건당(전 구간 2010~):")
    for lo, hi in ((0, 100), (100, 150), (150, 200), (200, 300), (300, 500), (500, 1000), (1000, 1e9)):
        z = W[(mc >= lo) & (mc < hi)]
        print("  %s~%s억: %s" % (lo, "" if hi > 1e8 else int(hi), cell(z)))
    z = W[mc < 150]
    print("\n시총 150억 미만 최악 5:", ", ".join("%s %s(%.0f억) %+.1f" % (r.date, r.ticker, r.mcap, r.oc) for r in z.nsmallest(5, "oc").itertuples()))


if __name__ == "__main__":
    main()
