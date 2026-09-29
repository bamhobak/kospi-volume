# -*- coding: utf-8 -*-
"""[자사주 낙폭] N4 를 빼면 미장 계좌가 좋아지나 — 사이트 6규칙 계좌로 확인 (2026-09-30 사용자 질문).
us_capture.py 의 준비 부분(패널·신호·경로·sim)을 그대로 쓰고, N4 유무만 바꿔 50시드 비교한다.
    python research/us_n4_check.py
"""
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent
src = (ROOT / "us_capture.py").read_text(encoding="utf-8")
src = src.split("# ── ① 미장 계좌")[0]
ns = {"__file__": str(ROOT / "us_capture.py"), "__name__": "us_capture_prep"}
exec(compile(src, "us_capture.py", "exec"), ns)
np, pd = ns["np"], ns["pd"]
S, PATH, sim, metrics, SPX, ud = ns["S"], ns["PATH"], ns["sim"], ns["metrics"], ns["SPX"], ns["ud"]
PCT, MX, yearly = ns["PCT"], ns["MX"], ns["yearly"]
OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))


def run(mask, seeds=50):
    Sx = S[mask].reset_index(drop=True)
    ns["PATH_X"] = [PATH[i] for i in S.index[mask]]
    navs = pd.concat([sim(Sx, PCT, MX, s)[0] for s in range(seeds)], axis=1)
    return navs


def cagr(nav, a):
    z = nav[nav.index >= a]; z = z / z.iloc[0]
    return ((z.iloc[-1]) ** (252 / len(z)) - 1) * 100, (z / z.cummax() - 1).min() * 100


t0 = time.time()
base = run(pd.Series(True, index=S.index).values)
no4 = run((S.rid != "N4").values)
P("# [자사주 낙폭] 빼면 미장 계좌가 좋아지나 · 사이트 6규칙(N1~N6) · 50시드 · %s" % time.strftime("%Y-%m-%d")); P("")
P("| 기간 | 6규칙 그대로 연수익 · 최대낙폭 | N4 빼면 | N4 뺀 쪽이 이긴 시드 |"); P("|---|---|---|---|")
for a in ("20160101", "20210101", "20230101"):
    b = [cagr(base[c], a) for c in base.columns]; n = [cagr(no4[c], a) for c in no4.columns]
    win = np.mean([n[i][0] > b[i][0] for i in range(len(b))]) * 100
    P("| %s~ | %+.1f%% · %.1f%% | %+.1f%% · %.1f%% | %.0f%% |" % (a[2:4], np.median([x[0] for x in b]), np.median([x[1] for x in b]),
                                                          np.median([x[0] for x in n]), np.median([x[1] for x in n]), win))
P(""); P("### 연도별(시드 중앙 NAV)"); P("")
yb, yn = yearly(base.median(axis=1)), yearly(no4.median(axis=1))
P("| 연도 | 6규칙 | N4 빼면 | 차이 |"); P("|---|---|---|---|")
for y in yb.index:
    P("| %s | %+.1f%% | %+.1f%% | %+.1f%%p |" % (y, yb[y], yn[y], yn[y] - yb[y]))
# N4 거래 자체(2016~ 끝난 거래)
idx = S.index[(S.rid == "N4")]
r = []
for i in idx:
    ddi, ratio = PATH[i]
    if len(ddi) and ddi[-1] >= S.di[i] + S.hold[i] - 3:
        r.append(((ratio[-1] - 1) * 100 - S.cost[i], S.date[i][:4]))
R = pd.DataFrame(r, columns=["r", "y"])
P(""); P("### N4 거래 자체 (2016~ · 60일 보유 끝난 것)"); P("")
P("| 연도 | 거래 | 평균 | 중앙 | 승률 |"); P("|---|---|---|---|---|")
for y, g in R.groupby("y"):
    P("| %s | %d | %+.2f | %+.2f | %.0f%% |" % (y, len(g), g.r.mean(), g.r.median(), (g.r > 0).mean() * 100))
P("| 전체 | %d | %+.2f | %+.2f | %.0f%% |" % (len(R), R.r.mean(), R.r.median(), (R.r > 0).mean() * 100))
P(""); P("(%.0f분)" % ((time.time() - t0) / 60))
(ROOT / "reports" / ("us_n4_check_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")
