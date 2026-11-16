# -*- coding: utf-8 -*-
"""H0424 덧대기: 공매도 과열종목 지정 직후 종목을 지금 규칙이 살 때 — 빼는 게 나은가 (2026-11-17).
T1 [갭하락](매수 = 그날 시가): 전날 저녁 지정(= 오늘이 금지 날) / 2~3일 전 지정.  스윙(신호 날 다음 시가 매수): 신호 날 포함 최근 1·3·5일 안 지정.
같은 날 짝: 걸린 거래 − 같은 날 안 걸린 거래 평균. 학습 17~22 / 검증 23~.
"""
import math, pickle, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parent.parent
OUT = []; P_ = lambda s="": (OUT.append(s), print(s, flush=True))
t_ = lambda s: s.mean() / s.std(ddof=1) * math.sqrt(len(s)) if len(s) > 2 and s.std(ddof=1) > 0 else 0.0
c = sqlite3.connect("file:%s?mode=ro" % (BASE / "data" / "dart" / "kind_time.db"), uri=True)
K = pd.read_sql("select day, kcode from kind where title like '공매도 과열종목 지정%'", c); c.close()
K["t"] = K.kcode + "0"
d1 = pickle.load(open("C:/temp/kp/kind/t1.pkl", "rb")); cal = d1["cal"]; ci = {d: i for i, d in enumerate(cal)}
K = K[K.day.isin(ci)]; K["i"] = K.day.map(ci)
last = {}
for t, g in K.groupby("t"): last[t] = np.sort(g.i.values)
PER = (("학습 17~22", "20170414", "20221231"), ("검증 23~", "20230101", "20991231"))


def ago(T, shift):                       # 매수 직전까지 알 수 있는 가장 최근 지정이 며칠 전인가(거래일). shift: T1 = 1(전날 저녁까지), 스윙 = 0(신호 날 저녁까지)
    out = np.full(len(T), 999)
    for n, (t, d) in enumerate(zip(T.ticker.values, T.date.values)):
        a = last.get(t); i = ci.get(d)
        if a is None or i is None: continue
        k = np.searchsorted(a, i - shift, side="right") - 1
        if k >= 0: out[n] = (i - shift) - a[k]
    return out


def tab(name, T, shift, wins):
    T = T[T.date >= "20170414"].copy(); T["ago"] = ago(T, shift)
    for wn, lo, hi in wins:
        hit = (T.ago >= lo) & (T.ago <= hi); cells = []
        for _, a, b in PER:
            z = T[(T.date >= a) & (T.date <= b)]; h = z[hit[z.index]]; o = z[~hit[z.index]]
            if len(h) < 8: cells.append("%d건 | – | – | –" % len(h)); continue
            pr = (h.groupby("date").r.mean() - o.groupby("date").r.mean()).dropna()
            cells.append("%d건(%.1f%%) | %+.2f%% (승 %.0f%%) | %+.2f%% | %+.2f (t%.1f·%d날)" % (len(h), len(h) / len(z) * 100, h.r.mean(), (h.r > 0).mean() * 100, o.r.mean(), pr.mean() if len(pr) else float("nan"), t_(pr), len(pr)))
        P_("| %s | %s | %s | %s |" % (name, wn, cells[0], cells[1]))


P_("# H0424 덧대기 — 공매도 과열 지정 직후 종목을 지금 규칙이 살 때\n")
P_("| 규칙 | 지정 시점 | 학습 걸린 건 | 걸린 거래 건당 | 안 걸린 거래 | 같은 날 짝(t) | 검증 걸린 건 | 걸린 거래 | 안 걸린 거래 | 같은 날 짝(t) |\n|---|---|---|---|---|---|---|---|---|---|")
tab("[갭하락] T1", d1["T"], 1, (("전날 저녁(오늘 금지)", 0, 0), ("2~3일 전", 1, 2), ("최근 5일 안", 0, 4)))
sw = pickle.load(open("C:/temp/kp/kind/swing.pkl", "rb"))
for rid, v in sw.items():
    tab("[%s] %s·%d일" % (v["name"], v["disp"], v["hold"]), v["T"], 0, (("신호 날 저녁", 0, 0), ("최근 3일 안", 0, 2), ("최근 10일 안", 0, 9)))
ALL = pd.concat([v["T"] for v in sw.values()], ignore_index=True)
tab("스윙 전체", ALL, 0, (("신호 날 저녁", 0, 0), ("최근 3일 안", 0, 2), ("최근 10일 안", 0, 9)))
(BASE / "research" / "reports" / "ssban_filter_1117.md").write_text("\n".join(OUT), encoding="utf-8")
