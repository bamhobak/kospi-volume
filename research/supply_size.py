# -*- coding: utf-8 -*-
"""공급계약을 '규모(매출액 대비 %)'로 나누기 (2026-10-02 사용자 제안 9번).
재료: research/cache/supply_kr.pkl(fetch_supply_kr.py · DART 원문의 '매출액대비(%)') · 2016~ · 거래대금 3억↑ 종목.
칸: 규모 구간(10% 미만 / 10~30 / 30~50 / 50% 이상 / 100% 이상) × 진입 0·5·21 × 보유 20·60. 잣대는 event_lab 과 같다.
    python research/supply_size.py
"""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
import event_lab as E

E.OUT.clear(); P = E.P


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    S = pd.read_pickle(ROOT / "cache" / "supply_kr.pkl").dropna(subset=["pct"])
    S = S.drop_duplicates("rcept_no")
    L = E.Lab()
    P("# 공급계약 — 규모(매출액 대비 %%)로 나누기 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("원문에서 숫자를 뽑은 공시 %s건 · 규모 중앙 %.1f%% · 50%%↑ %d건 · 100%%↑ %d건" % (f"{len(S):,}", S.pct.median(), (S.pct >= 50).sum(), (S.pct >= 100).sum())); P("")
    G_ = [("10% 미만", S[S.pct < 10]), ("10~30%", S[(S.pct >= 10) & (S.pct < 30)]), ("30~50%", S[(S.pct >= 30) & (S.pct < 50)]),
          ("50% 이상", S[S.pct >= 50]), ("100% 이상", S[S.pct >= 100]), ("전부", S)]
    for nm, z in G_:
        e = list(zip(z.ticker.values, z.date.values))
        for k in (0, 5, 21):
            for h in (20, 60):
                L.cell("공급계약", nm, e, k, h)
    G, zc = L.judge()
    G.to_pickle(ROOT / "cache" / "supply_size.pkl")
    P("칸 %d개 · 본페로니 t ≥ %.2f · 통과 %d칸 · 근접 %d칸" % (len(G), zc, G["pass"].sum(), G.near.sum())); P("")
    P("| 규모 | 진입 | 보유 | 건수(학·검) | 학습 중앙·초과·승률 | 검증 중앙·초과·승률 | t | 양수 해 | 판정 |"); P("|---|---|---|---|---|---|---|---|---|")
    f = lambda v: "%+.2f" % v if v == v else "-"
    for _, x in G.iterrows():
        P("| %s | +%d일 | %d일 | %d·%d | %s · %s · %s | %s · %s · %s | %s | %d/%d | %s |" % (
            x["name"], x.k, x.h, x.n1, x.n2, f(x.med1), f(x.ex1), ("%.0f%%" % x.win1) if x.win1 == x.win1 else "-",
            f(x.med2), f(x.ex2), ("%.0f%%" % x.win2) if x.win2 == x.win2 else "-", ("%.1f" % x.t) if x.t == x.t else "-", x.ypos, x.ny,
            "✅ 통과" if x["pass"] else ("△ 근접" if x.near else "")))
    P(""); P("(%.0f분)" % ((time.time() - t0) / 60))
    (ROOT / "reports" / ("supply_size_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(E.OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
