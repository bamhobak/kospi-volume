# -*- coding: utf-8 -*-
"""국내 규칙 보유기간 점검 — 규칙 **각각 단독**으로, 두 기간 모두에서 (2026-09-24).

미장 [저PBR 낙폭]을 40→60일로 바꾼 시험(n3_tune.py)을 국내 9규칙에도 댄다. hold_sweep_us.py 의 짝.
잣대: portfolio.py 의 규칙 정의(RULES) 그대로 · 수익 = 청산가/매수가 - 비용(portfolio.py simulate 와 같은 식) ·
신호 나면 다 산다 · 한 종목 보유 중 재신호 무시.
기간: A 2005~2015(홀드아웃) · B 2016~. 가격제한폭 ±15% 시절(A 대부분)은 반등이 깎여 A 가 보수적으로 나온다.
판정(미리 정함): 다른 보유가 **A·B 둘 다** 평균과 승률에서 지금 보유를 이길 때만 '손볼 후보'.
[저PBR 낙폭(코스닥)]은 PBR 이 2019-04~ 만 있어 A 를 못 잰다. [외인 매집]은 2018~22 시총 결측.

    python hold_sweep_kr.py
"""
import sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
SRC = (BASE / "portfolio.py").read_text(encoding="utf-8")
HEAD = SRC.split("# 신호를 한 표로 모은다", 1)[0]
ns = {"__file__": str(BASE / "portfolio.py")}
exec(compile(HEAD, "portfolio.py", "exec"), ns)
sys.stdout.reconfigure(encoding="utf-8")
RULES = ns["RULES"]
NAME = {"P1": "조용한 신고가", "P2": "조정매집", "P3": "폭락반등", "P4": "업종붕괴 이탈", "P5": "자사주 낙폭",
        "P6": "깊은 이격", "P7": "외인 매집", "D1": "낙폭과대", "D2": "저PBR 낙폭(코스닥)"}


def tries(h):
    return {40: (20, 40, 60), 10: (5, 10, 20), 20: (10, 20, 40), 5: (3, 5, 10), 60: (40, 60, 90)}[h]


def sig(K, cond, h):
    g = K.groupby("ticker", sort=False)
    di = g.cumcount()
    X = K[cond.fillna(False)].copy()
    X["exit"] = g.close.shift(-h).reindex(X.index)
    X["di"] = di.reindex(X.index)
    X = X.dropna(subset=["buy", "exit", "cost"])
    X = X[X.buy > 0].sort_values(["date"])
    keep, last = [], {}
    for t, d_, i, ix in zip(X.ticker.values, X.date.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h
        keep.append(ix)
    X = X.loc[keep]
    X["r"] = (X.exit / X.buy - 1) * 100 - X.cost
    return X[X.date >= "20050101"]


def st(z):
    r = z.r
    if len(r) < 5:
        return None
    ys = z.groupby(z.date.str[:4]).r.agg(["size", "mean"]); ys = ys[ys["size"] >= 5]
    return dict(n=len(r), avg=r.mean(), med=r.median(), win=(r > 0).mean() * 100,
                trim=r[r <= r.quantile(0.95)].mean(), yp=f"{(ys['mean'] > 0).sum()}/{len(ys)}")


f = lambda s: "—" if s is None else f"{s['n']:,}건 · 평균 {s['avg']:+.2f} · 중앙 {s['med']:+.2f} · 승률 {s['win']:.0f}% · 상위5%뺀 {s['trim']:+.2f} · 양수해 {s['yp']}"
print("\n## 국내 — 보유기간별 건당 성적 (규칙 단독, 비용 차감)\n")
print("| 규칙 | 보유 | A 2005~15 | B 2016~ |")
print("|---|---|---|---|")
VERD = {}
for rid, (K, hold, stop, pct, mx, cond) in RULES.items():
    R = {}
    for h in tries(hold):
        Z = sig(K, cond, h)
        R[h] = (st(Z[Z.date <= "20151231"]), st(Z[Z.date >= "20160101"]))
        tag = " **(지금)**" if h == hold else ""
        print(f"| [{NAME[rid]}] | {h}일{tag} | {f(R[h][0])} | {f(R[h][1])} |", flush=True)
    a0, b0 = R[hold]
    VERD[rid] = (hold, [h for h in tries(hold) if h != hold and all(
        x is not None and y is not None and x["avg"] > y["avg"] and x["win"] > y["win"]
        for x, y in ((R[h][0], a0), (R[h][1], b0)))])
print("\n## 판정 — 두 기간 모두 평균·승률이 나은 보유\n")
for rid, (hold, b) in VERD.items():
    print(f"- [{NAME[rid]}] 지금 {hold}일 → " + (f"**후보 {b}일**" if b else "그대로"))
