# -*- coding: utf-8 -*-
"""필터 수익이 실력인가 시장에 얹힌 것인가 — 같은 보유구간 시장수익 대비 초과수익 측정"""
import io, pickle, sqlite3, sys
import numpy as np, pandas as pd
import FinanceDataReader as fdr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
YS = list(range(2019, 2027))
S = [s for s in pickle.load(open("data/sig_2018.pkl", "rb")) if len(s["C"]) >= 2]

con = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True)
dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily ORDER BY date")]; con.close()
POS = {d: i for i, d in enumerate(dates)}
ki = fdr.DataReader("KS11", "2017-12-01"); ki = ki[ki["Close"] > 0]
ki.index = ki.index.strftime("%Y%m%d")
KO = ki["Open"].to_dict(); KC = ki["Close"].to_dict()

def cost(a):
    a = a or 3
    return 0.18 + (0.20 if a >= 100 else 0.30 if a >= 50 else 0.50 if a >= 20 else 0.70 if a >= 10 else 1.00)
def ev2(s, h, sl, tp):
    """(순수익, 보유일수) — 보유일수는 실제 청산까지의 거래일"""
    H, L, C = s["H"], s["L"], s["C"]; n = min(h, len(C) - 1); c = cost(s["amt"])
    for i in range(n + 1):
        if sl and L[i] <= -sl: return -sl - c, i
        if tp and H[i] >= tp: return tp - c, i
        if i == n: return C[i] - c, i
def mkt(s, hh):
    """같은 구간 코스피 수익 (신호 다음날 시가 → hh거래일 뒤 종가)"""
    p = POS.get(s["d"])
    if p is None or p + 1 + hh >= len(dates): return None
    d0, d1 = dates[p + 1], dates[p + 1 + hh]
    o, c = KO.get(d0), KC.get(d1)
    if not o or not c: return None
    return (c / o - 1) * 100

def analyze(P, h, sl, tp, lab):
    rows = []
    for s in P:
        r, hh = ev2(s, h, sl, tp)
        m = mkt(s, hh)
        if m is None: continue
        rows.append((s["y"], r, m, r - m))
    if not rows: return
    df = pd.DataFrame(rows, columns=["y", "ret", "mkt", "alpha"])
    print(f"\n## {lab}\n")
    print("| 연도 | 건수 | 필터 수익 | 같은구간 시장 | **초과수익** | 초과 승률 |")
    print("|---|---|---|---|---|---|")
    for y in YS:
        g = df[df.y == y]
        if len(g) < 3: print(f"| {y} | {len(g)} | - | - | - | - |"); continue
        print(f"| {y} | {len(g)} | {g.ret.mean():+.2f}% | {g.mkt.mean():+.2f}% | **{g.alpha.mean():+.2f}%** | {(g.alpha>0).mean()*100:.0f}% |")
    for nm, lo, hi in [("2019~2022", 2019, 2022), ("2023~2026", 2023, 2026), ("**전체**", 2019, 2026)]:
        g = df[(df.y >= lo) & (df.y <= hi)]
        print(f"| {nm} | {len(g)} | {g.ret.mean():+.2f}% | {g.mkt.mean():+.2f}% | **{g.alpha.mean():+.2f}%** | {(g.alpha>0).mean()*100:.0f}% |")

F1 = lambda s: (s["quiet"] < 0.5 and s["surge"] >= 2 and s["fwp"] >= 2 and s["amt"] >= 50
                and 0 <= s["ret10"] <= 20 and s["k20"] and not s["pref"] and s["rs"] is not None and s["rs"] > 0)
F2 = lambda s: (s["quiet"] < 0.4 and s["surge"] >= 2 and s["fwp"] >= 2 and s["amt"] >= 3
                and s["ret3"] <= 0 and not s["pref"])
analyze([s for s in S if F1(s)], 10, 15, 30, "1번 필터 (10일·손절15%·익절30%)")
analyze([s for s in S if F2(s)], 10, 10, None, "2번 필터 (10일·손절10%)")
analyze(S, 10, None, None, "기준선 — 전체 신호 (필터 없음)")
