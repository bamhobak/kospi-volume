# -*- coding: utf-8 -*-
"""[갭 하락 조용주] 유망 축 결합 + 계좌 기준 수익·낙폭 (2026-10-26).
초소형(mcap 하위30%)·장기하락(120일선 하위30%)을 결합/top-N 하고, H0362 방식
(계좌 20%를 그날 후보에 균등, 신호 없는 날은 현금=0, 일복리)으로 연수익·최대낙폭·날승률을 2016~·2023~ 로.
    py314 research/day_tune2_1026.py
"""
import sys, time
from pathlib import Path
ROOT = Path(r'C:\vscode\kospi-volume\research')
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'factory')); sys.path.insert(0, str(ROOT.parent))
sys.stdout.reconfigure(encoding='utf-8')
import numpy as np, pandas as pd
import lab

COST = 0.22
BUDGET = 0.20
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
CAL = []


def acct(z, lo, hi):
    z = z[(z.date >= lo) & (z.date <= hi)]
    if z.date.nunique() < 60:
        return None
    day = z.groupby("date").ocn.mean() / 100.0
    cal = [d for d in CAL if lo <= d <= hi]
    r = day.reindex(cal).fillna(0.0)
    eq = (1 + BUDGET * r).cumprod()
    yrs = len(r) / 252.0
    cagr = (eq.iloc[-1] ** (1 / yrs) - 1) * 100
    dd = (eq / eq.cummax() - 1).min() * 100
    return cagr, dd, (day > 0).mean() * 100, len(z) / yrs


def line(label, z):
    a, b = acct(z, "20160101", "20991231"), acct(z, "20230101", "20991231")
    f = lambda a: ("연%+.1f%%·낙%.1f%%·날승%.0f%%·연%.0f건" % a) if a else "-"
    P("| %s | %s | %s |" % (label, f(a), f(b)))


def main():
    t0 = time.time()
    global CAL
    Hall = lab.hist()
    CAL = sorted(Hall.date.unique())
    H = Hall[Hall.t1].copy()
    H["ocn"] = H.oc.clip(-60, 60) - COST
    H = H.dropna(subset=["ocn"])
    H["qm"] = H.groupby("date").mcap.rank(pct=True)
    small = H.qm <= 0.30
    downt = H.q_d120 <= 0.30

    def topn(z, n):
        z = z.copy(); z["rk"] = z.groupby("date").rgap.rank(method="first"); return z[z.rk <= n]

    P("# [갭 하락 조용주] 축 결합 · 계좌 기준 · %s" % time.strftime("%Y-%m-%d"))
    P("(계좌 20%%를 그날 후보에 균등, 신호 없는 날 현금, 일복리, 비용 %.2f%%)" % COST); P("")
    P("| 설정 | 2016~ (연수익·최대낙폭·날승률·연건수) | 2023~ |"); P("|---|---|---|")
    line("기본 T1(전부)", H)
    line("초소형(시총 하위30%)", H[small])
    line("장기하락(120일선 하위30%)", H[downt])
    line("초소형 × 장기하락", H[small & downt])
    line("초소형 × 하루 깊은 3개", topn(H[small], 3))
    line("초소형 × 하루 깊은 5개", topn(H[small], 5))
    line("장기하락 × 하루 깊은 3개", topn(H[downt], 3))
    line("초소형 × 장기하락 × 깊은 5개", topn(H[small & downt], 5))
    line("(참고) 하루 깊은 3개 = H0362", topn(H, 3))

    P(""); P("### 연도별 날바구니 평균%% (초소형 × 장기하락)"); P("")
    z = H[small & downt]
    yb = z.groupby(z.date.str[:4]).ocn.mean(); yn = z.groupby(z.date.str[:4]).size()
    P("| 연 | " + " | ".join(yb.index) + " |"); P("|" + "---|" * (len(yb) + 1))
    P("| 날% | " + " | ".join("%+.2f" % v for v in yb.values) + " |")
    P("| 건 | " + " | ".join("%d" % v for v in yn.values) + " |")

    (ROOT / "reports" / ("day_tune2_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")
    P(""); P("(%.0f초)" % (time.time() - t0))


if __name__ == "__main__":
    main()
