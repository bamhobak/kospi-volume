# -*- coding: utf-8 -*-
"""커뮤니티 개인 매매법 8종 실측 — 지수 대비 초과수익 · 1일 지연 · 비용 반영"""
import io, sqlite3, sys
import numpy as np, pandas as pd
import FinanceDataReader as fdr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
NB, MINGAP = 70, 10
con = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True)
df = pd.read_sql("""SELECT date,ticker,close,volume,frgn,organ,open,high,low FROM daily
   WHERE market='KOSPI' AND close IS NOT NULL AND open>0 ORDER BY ticker,date""", con)
dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily ORDER BY date")]; con.close()
POS = {d: i for i, d in enumerate(dates)}
ki = fdr.DataReader("KS11", "2017-12-01"); ki = ki[ki.Close > 0]; ki.index = ki.index.strftime("%Y%m%d")
KO, KC = ki["Open"].to_dict(), ki["Close"].to_dict()
K20 = (ki["Close"] > ki["Close"].rolling(20).mean()).to_dict()

def cost(a):
    a = a or 3
    return 0.18 + (0.20 if a >= 100 else 0.30 if a >= 50 else 0.50 if a >= 20 else 0.70 if a >= 10 else 1.00)
def ev2(s, h, sl=None, tp=None, stop_px=None):
    H, L, C, c = s["H"], s["L"], s["C"], cost(s["amt"]); n = min(h, len(C) - 1)
    for i in range(n + 1):
        if stop_px is not None and L[i] <= stop_px: return stop_px - c, i
        if sl and L[i] <= -sl: return -sl - c, i
        if tp and H[i] >= tp: return tp - c, i
        if i == n: return C[i] - c, i
def mkt(s, hh):
    p = POS.get(s["d"])
    if p is None or p + 1 + hh >= len(dates): return None
    o, c = KO.get(dates[p + 1]), KC.get(dates[p + 1 + hh])
    return None if not o or not c else (c / o - 1) * 100
def A(P, h, sl=None, tp=None, mn=20, stopkey=None):
    rows = []
    for s in P:
        r, hh = ev2(s, h, sl, tp, s.get(stopkey) if stopkey else None); m = mkt(s, hh)
        if m is None: continue
        rows.append((s["y"], r, r - m))
    if len(rows) < mn: return None
    d = pd.DataFrame(rows, columns=["y", "ret", "al"])
    yy = d.groupby("y").al.mean(); cnt = d.groupby("y").size(); ok = yy[cnt >= 3]
    return dict(n=len(d), ret=d.ret.mean(), al=d.al.mean(), med=d.al.median(),
                win=(d.ret > 0).mean() * 100, alwin=(d.al > 0).mean() * 100, pos=f"{(ok>0).sum()}/{len(ok)}")
def show(t, rows):
    print(f"\n## {t}\n"); print("| 설정 | 건수 | 절대수익 | **초과수익** | 초과중앙값 | 승률 | 초과승률 | 초과+ 연도 |\n|---|---|---|---|---|---|---|---|")
    for lab, a in rows:
        if not a: print(f"| {lab} | 부족 |" + " - |" * 6); continue
        print(f"| {lab} | {a['n']} | {a['ret']:+.2f}% | **{a['al']:+.2f}%** | {a['med']:+.2f}% | {a['win']:.0f}% | {a['alwin']:.0f}% | {a['pos']} |")

# ── 피처 사전 계산 (종목별)
SIGS = {k: [] for k in ("A", "B", "C", "D", "E", "F", "G", "H")}
for t, g in df.groupby("ticker", sort=False):
    if len(g) < 300 or not t.endswith("0"): continue
    g = g.reset_index(drop=True)
    C, O, H, L = (pd.Series(g[c].values, dtype="float64") for c in ("close", "open", "high", "low"))
    V = pd.Series(g["volume"].values, dtype="float64")
    F = pd.Series(g["frgn"].values, dtype="float64").fillna(0)
    R = pd.Series(g["organ"].values, dtype="float64").fillna(0)
    D = g["date"].values
    ma5, ma20, ma60, ma120 = C.rolling(5).mean(), C.rolling(20).mean(), C.rolling(60).mean(), C.rolling(120).mean()
    v5, v20, v60 = V.rolling(5).mean(), V.rolling(20).mean(), V.rolling(60).mean()
    amt = (V * C).rolling(20).mean() / 1e8
    ret1 = C.pct_change() * 100
    hi52 = H.rolling(240).max(); hi120 = H.rolling(120).max()
    fpos = (F > 0).astype(int); rpos = (R > 0).astype(int)
    f3 = fpos.rolling(3).sum(); r3 = rpos.rolling(3).sum()
    f5 = fpos.rolling(5).sum()
    def push(key, j, extra=None):
        if j + 1 >= len(g): return
        o0 = O[j + 1]
        if not np.isfinite(o0) or o0 <= 0: return
        e = min(j + 1 + NB, len(g))
        s = dict(t=t, d=D[j], y=int(D[j][:4]), amt=float(amt[j]) if np.isfinite(amt[j]) else 0.0,
                 H=(H[j+1:e].values/o0-1)*100, L=(L[j+1:e].values/o0-1)*100, C=(C[j+1:e].values/o0-1)*100,
                 k20=bool(K20.get(D[j], False)))
        if extra: s.update(extra)
        SIGS[key].append(s)
    last = {k: -99 for k in SIGS}
    for j in range(240, len(g) - 1):
        # A. 골든크로스: 5일선이 20일선 상향 돌파 (가장 많이 언급)
        if ma5[j] > ma20[j] and ma5[j-1] <= ma20[j-1] and j - last["A"] >= MINGAP:
            push("A", j, dict(above60=bool(C[j] > ma60[j]))); last["A"] = j
        # B. 정배열 눌림목: 정배열 + 20일선 터치(±2%) + 조정 중 거래량 급감 + 양봉
        if (ma5[j] > ma20[j] > ma60[j] and abs(C[j]/ma20[j]-1) < 0.02 and C[j] > O[j]
            and v5[j] < 0.5 * v20[j-5] and j - last["B"] >= MINGAP):
            push("B", j, dict(stop=(ma20[j]/O[j+1]-1)*100 - 2)); last["B"] = j
        # C. 키움 세력매집식: 거래량 5일평균 150%↑ + 외국인·기관 3일 연속 순매수 + 시총(대금)조건
        if (V[j] >= 1.5 * v5[j-1] and f3[j] == 3 and r3[j] == 3 and j - last["C"] >= MINGAP):
            push("C", j); last["C"] = j
        # D. 전고점(120일) 돌파 + 거래량 2배
        if (C[j] > hi120[j-1] and V[j] >= 2 * v20[j-1] and j - last["D"] >= MINGAP):
            push("D", j, dict(stop=(L[j]/O[j+1]-1)*100)); last["D"] = j
        # E. 52주 신고가 + 거래량 2배 + 정배열
        if (C[j] > hi52[j-1] and V[j] >= 2 * v20[j-1] and C[j] > ma20[j] > ma60[j] > ma120[j]
            and j - last["E"] >= MINGAP):
            push("E", j, dict(stop=(L[j]/O[j+1]-1)*100)); last["E"] = j
        # F. 장대양봉(+7%↑, 거래량 3배) 후 눌림: 3~7일 뒤 거래량이 장대봉의 30% 이하 + 양봉
        for k in range(3, 8):
            jj = j - k
            if jj < 1: break
            if ret1[jj] >= 7 and V[jj] >= 3 * v20[jj-1] and V[j] <= 0.3 * V[jj] and C[j] > O[j] \
               and C[j] > C[jj] * 0.93 and j - last["F"] >= MINGAP:
                push("F", j, dict(stop=(L[jj]/O[j+1]-1)*100)); last["F"] = j; break
        # G. 외국인 5일 연속 순매수 (단순 수급)
        if f5[j] == 5 and f5[j-1] == 4 and j - last["G"] >= MINGAP:
            push("G", j); last["G"] = j
        # H. 외국인+기관 쌍끌이 3일 연속 (거래량 조건 없음)
        if f3[j] == 3 and r3[j] == 3 and f3[j-1] == 2 and j - last["H"] >= MINGAP:
            push("H", j); last["H"] = j
for k, v in SIGS.items(): print(f"{k}: {len(v):,}건", end="  ")
print()
def AMT(P, a=3): return [s for s in P if s["amt"] >= a]
show("A. 5일선/20일선 골든크로스 (디시 해외주식갤 등 최다 언급)",
     [(f"{h}일", A(AMT(SIGS["A"]), h)) for h in (5, 10, 20, 40)]
     + [("+60일선 위 · 10일", A([s for s in AMT(SIGS["A"]) if s["above60"]], 10)),
        ("+대금 50억 · 10일", A(AMT(SIGS["A"], 50), 10))])
show("B. 정배열 + 20일선 눌림목 + 거래량 급감 + 양봉 (눌림목 매매법)",
     [(f"{h}일", A(AMT(SIGS["B"]), h)) for h in (5, 10, 20, 40)]
     + [("10일 · 20일선 -2% 이탈 손절", A(AMT(SIGS["B"]), 10, stopkey="stop"))])
show("C. 키움 세력매집 검색식 (거래량150% + 외인·기관 3일 연속)",
     [(f"{h}일", A(AMT(SIGS["C"]), h)) for h in (3, 5, 10, 20)]
     + [("+대금 50억(시총 대용) · 10일", A(AMT(SIGS["C"], 50), 10))])
show("D. 120일 전고점 돌파 + 거래량 2배 (전고점 돌파 매매)",
     [(f"{h}일", A(AMT(SIGS["D"]), h)) for h in (1, 2, 5, 10, 20)]
     + [("10일 · 돌파봉 저점 손절", A(AMT(SIGS["D"]), 10, stopkey="stop"))])
show("E. 52주 신고가 + 거래량 2배 + 정배열 (신고가 매매)",
     [(f"{h}일", A(AMT(SIGS["E"]), h)) for h in (5, 10, 20, 40)]
     + [("10일 · 돌파봉 저점 손절", A(AMT(SIGS["E"]), 10, stopkey="stop"))])
show("F. 장대양봉 후 거래량 마른 눌림 + 양봉 (세력 미이탈 눌림목)",
     [(f"{h}일", A(AMT(SIGS["F"]), h)) for h in (3, 5, 10, 20)]
     + [("10일 · 장대봉 저점 손절", A(AMT(SIGS["F"]), 10, stopkey="stop"))])
show("G. 외국인 5일 연속 순매수 (수급 매매)",
     [(f"{h}일", A(AMT(SIGS["G"]), h)) for h in (3, 5, 10, 20)])
show("H. 외국인+기관 쌍끌이 3일 연속 (클리앙 기관수급주 2~4일)",
     [(f"{h}일", A(AMT(SIGS["H"]), h)) for h in (2, 3, 5, 10, 20)])
