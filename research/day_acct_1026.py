# -*- coding: utf-8 -*-
"""[갭 하락 조용주] 장기하락 필터 넣으면 계좌가 어떻게 변하나 (2026-10-26, 사용자).
데이 계좌 방식 = H0362 와 동일(계좌의 20%를 그날 후보에 균등, 신호 없는 날 현금, 일복리).
지금(전부 T1) vs 장기하락(120일선 하위30%)을 연도별 계좌수익·누적배수·낙폭으로 나란히.
    py314 research/day_acct_1026.py
"""
import sys, time
from pathlib import Path
ROOT = Path(r'C:\vscode\kospi-volume\research')
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'factory')); sys.path.insert(0, str(ROOT.parent))
sys.stdout.reconfigure(encoding='utf-8')
import numpy as np, pandas as pd
import lab

COST, BUDGET = 0.22, 0.20
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def equity(z, cal):
    day = z.groupby("date").ocn.mean() / 100.0
    r = day.reindex(cal).fillna(0.0)
    return (1 + BUDGET * r).cumprod(), day


def summ(z, cal, lo):
    cal2 = [d for d in cal if d >= lo]
    eq, day = equity(z[z.date >= lo], cal2)
    yrs = len(cal2) / 252.0
    mult = eq.iloc[-1]
    cagr = (mult ** (1 / yrs) - 1) * 100
    mdd = (eq / eq.cummax() - 1).min() * 100
    wd = (day[day.index >= lo] > 0).mean() * 100
    return mult, cagr, mdd, wd


def main():
    t0 = time.time()
    Hall = lab.hist()
    cal = sorted(Hall.date.unique())
    H = Hall[Hall.t1].copy()
    H["ocn"] = H.oc.clip(-60, 60) - COST
    H = H.dropna(subset=["ocn"])
    H["qm"] = H.groupby("date").mcap.rank(pct=True)
    A = H                              # 전부
    B = H[H.q_d120 <= 0.30]            # 장기하락

    P("# [갭 하락 조용주] 장기하락 필터 계좌 변화 · %s" % time.strftime("%Y-%m-%d"))
    P("(계좌 20%%를 그날 후보에 균등·신호 없는 날 현금·일복리·비용 %.2f%%)" % COST); P("")
    P("| 기간 | 지금(전부 T1) | 장기하락(120일선 하위30%) |"); P("|---|---|---|")
    for lo, nm in (("20100101", "2010~"), ("20160101", "2016~"), ("20230101", "2023~")):
        a = summ(A, cal, lo); b = summ(B, cal, lo)
        fm = lambda s: "%.2f배 · 연%+.1f%% · 낙%.1f%% · 날승%.0f%%" % s
        P("| %s | %s | %s |" % (nm, fm(a), fm(b)))

    # 연도별 계좌 수익률
    P(""); P("### 연도별 계좌 수익률 (%)"); P("")
    yrs = sorted(set(d[:4] for d in cal if d >= "20100101"))
    def yret(z):
        out = {}
        for y in yrs:
            cy = [d for d in cal if d[:4] == y]
            eq, _ = equity(z[z.date.str[:4] == y], cy)
            out[y] = (eq.iloc[-1] - 1) * 100 if len(eq) else 0.0
        return out
    ya, yb = yret(A), yret(B)
    P("| 연 | " + " | ".join(yrs) + " |"); P("|" + "---|" * (len(yrs) + 1))
    P("| 지금 | " + " | ".join("%+.1f" % ya[y] for y in yrs) + " |")
    P("| 장기하락 | " + " | ".join("%+.1f" % yb[y] for y in yrs) + " |")
    na = sum(1 for y in yrs if ya[y] > 0); nb = sum(1 for y in yrs if yb[y] > 0)
    P(""); P("플러스 해: 지금 %d/%d · 장기하락 %d/%d · 최악 해: 지금 %+.1f%% · 장기하락 %+.1f%%" % (
        na, len(yrs), nb, len(yrs), min(ya.values()), min(yb.values())))

    (ROOT / "reports" / ("day_acct_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")
    P(""); P("(%.0f초)" % (time.time() - t0))


if __name__ == "__main__":
    main()
