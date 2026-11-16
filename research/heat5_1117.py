# -*- coding: utf-8 -*-
"""H0425 덧조건 굳히기 — 통과한 재료(단일가 첫날 거래대금)로 수익금이 실제 늘어나는가 (2026-11-17).
① 문턱 흔들기(이웃 칸) ② 해마다 ③ 금액 배분(큰 종목에 더) ④ 60일 오름폭과 겹치기 ⑤ 위험(낙폭·최악)"""
import math, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parent.parent
OUT = []; P_ = lambda s="": (OUT.append(s), print(s, flush=True))
t_ = lambda s: s.mean() / s.std(ddof=1) * math.sqrt(len(s)) if len(s) > 2 and s.std(ddof=1) > 0 else 0.0
X = pd.read_pickle("C:/temp/kp/heat_ev4.pkl"); X = X.dropna(subset=["a1e"]).sort_values("day")
L = X.day <= "20221231"
def cell(z, w=2.0):
    if len(z) < 10: return "%d | – | – | –" % len(z)
    d = z.groupby("day").rD.mean(); pnl = z.groupby("day").rD.sum() * w; eq = pnl.cumsum()
    return "%d | %+.2f%% (%+.2f·%.0f%%) t%.1f | %+.0f만 | %.0f만·%+.1f%%" % (len(z), z.rD.mean(), z.rD.median(), (z.rD > 0).mean() * 100, t_(d), pnl.sum(), (eq - eq.cummax()).min(), z.rD.min())
HD = "| 조건 | 학습 건 | 건당(중앙·승률) t | 200만씩 손익 | 낙폭·최악 건 | 검증 건 | 건당(중앙·승률) t | 200만씩 손익 | 낙폭·최악 건 |\n|---|---|---|---|---|---|---|---|---|"
P_("# H0425 덧조건 굳히기 — 단일가 첫날(D+1) 거래대금\n\n거래대금 자료 있는 %d건(학습 %d · 검증 %d)\n" % (len(X), L.sum(), (~L).sum()))
P_("## 1. 문턱 흔들기\n"); P_(HD)
for th in (0, 20, 30, 40, 50, 70, 100, 150, 200):
    m = X.a1e >= th; P_("| D+1 거래대금 %d억↑ | %s | %s |" % (th, cell(X[m & L]), cell(X[m & ~L])))
P_("\n구간별:\n"); P_(HD)
for a, b in ((0, 20), (20, 40), (40, 70), (70, 120), (120, 250), (250, 1e9)):
    m = (X.a1e >= a) & (X.a1e < b); P_("| %d~%s억 | %s | %s |" % (a, "%d" % b if b < 1e8 else "", cell(X[m & L]), cell(X[m & ~L])))
P_("\n## 2. 해마다(건당 · 건)\n\n| 해 | 전체 | 50억↑ | 50억↓ |\n|---|---|---|---|")
for y, z in X.groupby(X.day.str[:4]):
    a, b = z[z.a1e >= 50], z[z.a1e < 50]; P_("| %s | %+.2f (%d) | %+.2f (%d) | %+.2f (%d) |" % (y, z.rD.mean(), len(z), a.rD.mean(), len(a), b.rD.mean(), len(b)))
P_("\n## 3. 금액 배분(평균 건당 200만이 되게 맞춤 — 같은 돈으로 수익금 비교)\n\n| 방식 | 학습 손익(만) | 낙폭 | 검증 손익(만) | 낙폭 | 검증 연 평균 |\n|---|---|---|---|---|---|")
def alloc(nm, w):
    w = w / w[L].mean() * 2.0; r = []
    for m in (L, ~L):
        p = (X.rD[m] * w[m]).groupby(X.day[m]).sum(); eq = p.cumsum(); r += ["%+.0f" % p.sum(), "%.0f" % (eq - eq.cummax()).min()]
    P_("| %s | %s | %s | %s | %s | %+.0f |" % (nm, r[0], r[1], r[2], r[3], float(r[2]) / 3.87))
one = pd.Series(1.0, index=X.index)
alloc("전부 같은 금액", one); alloc("50억↑만(나머지 0)", (X.a1e >= 50).astype(float)); alloc("30억↑만", (X.a1e >= 30).astype(float)); alloc("100억↑만", (X.a1e >= 100).astype(float))
alloc("50억↑ 2배 · 아래 1배", np.where(X.a1e >= 50, 2.0, 1.0) * one); alloc("50억↑ 3배 · 아래 1배", np.where(X.a1e >= 50, 3.0, 1.0) * one)
alloc("거래대금 제곱근 비례(20~300억 안)", np.sqrt(X.a1e.clip(20, 300)))
P_("\n(금액을 안 맞추고 50억↑만 200만씩: 학습 %+.0f만 · 검증 %+.0f만 / 전부 200만씩: 학습 %+.0f만 · 검증 %+.0f만)" % (X.rD[L & (X.a1e >= 50)].sum() * 2, X.rD[~L & (X.a1e >= 50)].sum() * 2, X.rD[L].sum() * 2, X.rD[~L].sum() * 2))
P_("\n## 4. 60일 오름폭과 겹치기\n"); P_(HD)
for nm, m in (("50억↑ · 60일 +50%↓", (X.a1e >= 50) & (X.ret60 < 50)), ("50억↑ · 60일 +50~75%", (X.a1e >= 50) & (X.ret60 >= 50) & (X.ret60 < 75)), ("50억↑ · 60일 +75%↑", (X.a1e >= 50) & (X.ret60 >= 75)),
              ("50억↓ · 60일 +75%↑", (X.a1e < 50) & (X.ret60 >= 75)), ("50억↓ · 60일 +75%↓", (X.a1e < 50) & (X.ret60 < 75)),
              ("50억↑ · 외국인 5일 플러스", (X.a1e >= 50) & (X.f5 > 0)), ("50억↑ · 외국인 5일 마이너스", (X.a1e >= 50) & (X.f5 <= 0)),
              ("50억↑ · D+1 눌림(종가<D 종가)", (X.a1e >= 50) & (X.c1 < X.c0)), ("50억↑ · D+1 오름", (X.a1e >= 50) & (X.c1 >= X.c0)),
              ("50억↑ · 유가증권", (X.a1e >= 50) & (X.market == "유가증권")), ("50억↑ · 코스닥", (X.a1e >= 50) & (X.market == "코스닥"))):
    P_("| %s | %s | %s |" % (nm, cell(X[m & L]), cell(X[m & ~L])))
Z = X[X.a1e >= 50]
P_("\n## 5. 50억↑ 판 위험: 아래 5%% %+.1f · 아래 1%% %+.1f · 최악 %+.1f · 동시에 든 최대 건수는 전체 판보다 적음 · 연 %d건" % (Z.rD.quantile(.05), Z.rD.quantile(.01), Z.rD.min(), len(Z) / 10.9))
(BASE / "research" / "reports" / "heat5_1117.md").write_text("\n".join(OUT), encoding="utf-8")
