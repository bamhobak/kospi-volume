# -*- coding: utf-8 -*-
"""H0425 사는 때·파는 때 바꿔 보기 (2026-11-17 사용자 "매수 타이밍 매도 타이밍 바꿔서 더 나은 조건 있나").
① 일봉 격자(2016~, 전체·50억↑): 사는 때 D+1 시가/종가·D+2 시가/종가·D+3 시가 × 파는 때 D+2 종가 ~ D+5 종가
② 단일가 회차별 길(1분봉, 2023~): D 종가 = 0 으로 놓고 D+1~D+3 의 14회 단일가 + D+4 시가·종가까지 평균·중앙 길 → 어디가 바닥·꼭대기인가
③ 회차 격자: D+1·D+2 의 각 회차에 사서 D+3 의 각 회차에 팔기(비용 0.23 뒤)"""
import math, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parent.parent; COST = 0.23
OUT = []; P_ = lambda s="": (OUT.append(s), print(s, flush=True))
t_ = lambda s: s.mean() / s.std(ddof=1) * math.sqrt(len(s)) if len(s) > 2 and s.std(ddof=1) > 0 else 0.0
X = pd.read_pickle("C:/temp/kp/heat_ev4.pkl")
P = pd.read_pickle(BASE / "research" / "cache" / "factory_px.pkl"); P = P[P.date >= "20151001"]
cal = sorted(P.date.unique()); tk = sorted(P.ticker.unique()); ti = {t: i for i, t in enumerate(tk)}
W = lambda col: P.pivot(index="date", columns="ticker", values=col).reindex(index=cal, columns=tk).values.astype(np.float64)
OP, HI, CL = W("open"), W("high"), W("close"); del P
jj = X.t.map(ti).values; ii = X.i.values
px = {}
for k in range(0, 7):
    px["D+%d 시가" % k] = OP[ii + k, jj]; px["D+%d 종가" % k] = CL[ii + k, jj]
    X["lk%d" % k] = (CL[ii + k, jj] / CL[ii + k - 1, jj] - 1 >= 0.295) & (CL[ii + k, jj] == HI[ii + k, jj])        # 종가 상한가(못 삼)
    X["lo%d" % k] = (OP[ii + k, jj] / CL[ii + k - 1, jj] - 1 >= 0.25)
BUY = ("D+1 시가", "D+1 종가", "D+2 시가", "D+2 종가", "D+3 시가"); SELL = ("D+2 종가", "D+3 시가", "D+3 종가", "D+4 시가", "D+4 종가", "D+5 종가")
order = ["D+%d %s" % (k, s) for k in range(0, 7) for s in ("시가", "종가")]
L = X.day <= "20221231"
def grid(title, M):
    P_("\n### %s\n\n| 사는 때 ↓ / 파는 때 → | %s |\n|---|%s" % (title, " | ".join(SELL), "---|" * len(SELL)))
    for b in BUY:
        k = int(b[2]); ok = ~(X["lk%d" % k] if "종가" in b else X["lo%d" % k]); cells = []
        for s in SELL:
            if order.index(s) <= order.index(b): cells.append("·"); continue
            r = pd.Series((px[s] / px[b] - 1) * 100 - COST, index=X.index); r[(r.abs() > 80)] = np.nan
            c2 = []
            for m in (L, ~L):
                z = r[M & ok & m].dropna(); d = z.groupby(X.day[z.index]).mean(); c2.append("%+.2f(%.0f%%·t%.1f)" % (z.mean(), (z > 0).mean() * 100, t_(d)))
            cells.append(" / ".join(c2))
        P_("| %s | %s |" % (b, " | ".join(cells)))
P_("# H0425 사는 때·파는 때 바꿔 보기\n\n## 1. 일봉 격자 — 칸 = 학습 건당(승률·t) / 검증 건당(승률·t), 비용 뒤, 상한가로 못 사는 건 뺌")
grid("전체(학습 %d · 검증 %d)" % (L.sum(), (~L).sum()), X.rD > -999)
grid("단일가 첫날 거래대금 50억↑ — D+1 시가 매수는 그 시점엔 거래대금을 모르니 참고만", X.a1e >= 50)
grid("지정 날(D) 거래대금 200억↑ (D+1 시가 전에 아는 조건)", X.amt >= 200)
# ② ③ 단일가 회차별
V = X[(X.day >= "20221201")].copy(); paths = []
for t, g in V.groupby("t"):
    f = BASE / "data" / "m1" / "KR" / "bf" / ("%s.parquet" % t)
    if not f.exists(): continue
    B = pd.read_parquet(f, columns=["ts", "c", "v"]); B = B[B.v > 0]
    k = pd.to_datetime(B.ts.values + 9 * 3600, unit="s"); B["d"] = k.strftime("%Y%m%d"); B["hm"] = k.strftime("%H%M")
    for _, r in g.iterrows():
        row = {"day": r.day, "t": t, "a1e": r.a1e, "c0": r.c0}; good = True
        for kk in (1, 2, 3):
            z = B[(B.d == cal[r.i + kk]) & (B.hm >= "0900") & (B.hm <= "1531")]
            if z.hm.nunique() < 10 or z.hm.nunique() > 16: good = False; break
            # 회차 = 30분 칸(0900→1, 0930→2 … 1500→13, 1530→14)
            mins = z.hm.str[:2].astype(int) * 60 + z.hm.str[2:].astype(int); slot = np.minimum(((mins - 540) // 30) + 1, 14)
            last = z.groupby(slot.values).c.last()
            for s in range(1, 15): row["%d-%02d" % (kk, s)] = last.get(s, np.nan)
        if not good: continue
        row["4-시가"], row["4-종가"] = r.o4, r.c4
        paths.append(row)
R = pd.DataFrame(paths); cols = ["%d-%02d" % (k, s) for k in (1, 2, 3) for s in range(1, 15)]
R[cols] = R[cols].ffill(axis=1)            # 체결 없는 회차 = 직전 값
lab = lambda c: "D+%s %s" % (c[0], ["", "09:00", "09:30", "10:00", "10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30(종가)"][int(c[2:])])
for nm, m in (("전체", R.a1e > -1), ("50억↑", R.a1e >= 50)):
    Z = R[m]; P_("\n## 2. 단일가 회차별 길 — %s (2022-12~ 1분봉 %d건, D 종가 대비 %%, 비용 전)\n\n| 회차 | 평균 | 중앙 | D 종가보다 위인 비율 |\n|---|---|---|---|" % (nm, len(Z)))
    for c in cols + ["4-시가", "4-종가"]:
        v = (Z[c] / Z.c0 - 1) * 100; P_("| %s | %+.2f | %+.2f | %.0f%% |" % (lab(c) if c in cols else "D+4 " + c[2:], v.mean(), v.median(), (v > 0).mean() * 100))
Z = R[R.a1e >= 50]
bs = ["1-01", "1-04", "1-07", "1-10", "1-13", "1-14", "2-01", "2-07", "2-14"]; ss = ["3-01", "3-04", "3-07", "3-10", "3-12", "3-13", "3-14", "4-시가"]
P_("\n## 3. 회차 격자 — 50억↑ %d건(2022-12~), 건당(승률·t), 비용 뒤\n\n| 사는 회차 ↓ / 파는 회차 → | %s |\n|---|%s" % (len(Z), " | ".join(lab(c) if c in cols else "D+4 시가" for c in ss), "---|" * len(ss)))
for b in bs:
    cells = []
    for s in ss:
        r = (Z[s] / Z[b] - 1) * 100 - COST; d = r.groupby(Z.day).mean(); cells.append("%+.2f(%.0f%%·t%.1f)" % (r.mean(), (r > 0).mean() * 100, t_(d)))
    P_("| %s | %s |" % (lab(b), " | ".join(cells)))
P_("\n같은 격자 전체 %d건:\n\n| 사는 회차 ↓ / 파는 회차 → | %s |\n|---|%s" % (len(R), " | ".join(lab(c) if c in cols else "D+4 시가" for c in ss), "---|" * len(ss)))
for b in bs:
    cells = []
    for s in ss:
        r = (R[s] / R[b] - 1) * 100 - COST; d = r.groupby(R.day).mean(); cells.append("%+.2f(%.0f%%·t%.1f)" % (r.mean(), (r > 0).mean() * 100, t_(d)))
    P_("| %s | %s |" % (lab(b), " | ".join(cells)))
(BASE / "research" / "reports" / "heat7_1117.md").write_text("\n".join(OUT), encoding="utf-8")
