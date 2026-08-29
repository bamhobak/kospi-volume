# -*- coding: utf-8 -*-
"""해외 커뮤니티·퀀트 사이트 스윙 기법 10종 실측 — 지수 대비 초과수익 · 1일 지연 · 비용 반영"""
import io, sqlite3, sys
import numpy as np, pandas as pd
import FinanceDataReader as fdr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
NB, MINGAP = 70, 10
con = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True)
df = pd.read_sql("""SELECT date,ticker,close,volume,open,high,low FROM daily
   WHERE market='KOSPI' AND close IS NOT NULL AND open>0 ORDER BY ticker,date""", con)
dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily ORDER BY date")]; con.close()
POS = {d: i for i, d in enumerate(dates)}
ki = fdr.DataReader("KS11", "2017-12-01"); ki = ki[ki.Close > 0]; ki.index = ki.index.strftime("%Y%m%d")
KO, KC = ki["Open"].to_dict(), ki["Close"].to_dict()

def cost(a):
    a = a or 3
    return 0.18 + (0.20 if a >= 100 else 0.30 if a >= 50 else 0.50 if a >= 20 else 0.70 if a >= 10 else 1.00)

def ev2(s, h, sl=None, tp=None, stop_px=None, exitkey=None):
    H, L, C, c = s["H"], s["L"], s["C"], cost(s["amt"]); n = min(h, len(C) - 1)
    ex = s.get(exitkey) if exitkey else None
    for i in range(n + 1):
        if stop_px is not None and L[i] <= stop_px: return stop_px - c, i
        if sl and L[i] <= -sl: return -sl - c, i
        if tp and H[i] >= tp: return tp - c, i
        if ex is not None and i < len(ex) and ex[i]: return C[i] - c, i
        if i == n: return C[i] - c, i

def mkt(s, hh):
    p = POS.get(s["d"])
    if p is None or p + 1 + hh >= len(dates): return None
    o, c = KO.get(dates[p + 1]), KC.get(dates[p + 1 + hh])
    return None if not o or not c else (c / o - 1) * 100

def A(P, h, sl=None, tp=None, mn=20, stopkey=None, exitkey=None):
    rows = []
    for s in P:
        r, hh = ev2(s, h, sl, tp, s.get(stopkey) if stopkey else None, exitkey); m = mkt(s, hh)
        if m is None: continue
        rows.append((s["y"], r, r - m, hh))
    if len(rows) < mn: return None
    d = pd.DataFrame(rows, columns=["y", "ret", "al", "hh"])
    yy = d.groupby("y").al.mean(); cnt = d.groupby("y").size(); ok = yy[cnt >= 3]
    return dict(n=len(d), ret=d.ret.mean(), al=d.al.mean(), med=d.al.median(), hh=d.hh.mean(),
                win=(d.ret > 0).mean() * 100, alwin=(d.al > 0).mean() * 100, pos=f"{(ok>0).sum()}/{len(ok)}")

def show(t, rows):
    print(f"\n## {t}\n")
    print("| 설정 | 건수 | 평균보유 | 절대수익 | **초과수익** | 초과중앙값 | 승률 | 초과승률 | 초과+ 연도 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for lab, a in rows:
        if not a: print(f"| {lab} | 부족 |" + " - |" * 7); continue
        print(f"| {lab} | {a['n']} | {a['hh']:.1f}일 | {a['ret']:+.2f}% | **{a['al']:+.2f}%** | {a['med']:+.2f}% | {a['win']:.0f}% | {a['alwin']:.0f}% | {a['pos']} |")

def rsi(c, n):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))

SIGS = {k: [] for k in "ABCDEFGHIJ"}
for t, g in df.groupby("ticker", sort=False):
    if len(g) < 300 or not t.endswith("0"): continue
    g = g.reset_index(drop=True)
    C, O, H, L = (pd.Series(g[c].values, dtype="float64") for c in ("close", "open", "high", "low"))
    V = pd.Series(g["volume"].values, dtype="float64"); D = g["date"].values
    ma5, ma20, ma25, ma200 = (C.rolling(n).mean() for n in (5, 20, 25, 200))
    e20, e50 = C.ewm(span=20, adjust=False).mean(), C.ewm(span=50, adjust=False).mean()
    v20 = V.rolling(20).mean(); amt = (V * C).rolling(20).mean() / 1e8
    r2, r14 = rsi(C, 2), rsi(C, 14)
    bb_m = C.rolling(20).mean(); bb_s = C.rolling(20).std(); bb_lo = bb_m - 2 * bb_s
    hi15 = H.rolling(15).max(); lo15 = L.rolling(15).min(); rng15 = (hi15 - lo15) / lo15
    hi20 = H.rolling(20).max(); swlo = L.rolling(10).min()
    n = len(g)

    def push(key, j, extra=None):
        if j + 1 >= n: return
        o0 = O[j + 1]
        if not np.isfinite(o0) or o0 <= 0: return
        e = min(j + 1 + NB, n)
        s = dict(t=t, d=D[j], y=int(D[j][:4]), amt=float(amt[j]) if np.isfinite(amt[j]) else 0.0,
                 H=(H[j+1:e].values/o0-1)*100, L=(L[j+1:e].values/o0-1)*100, C=(C[j+1:e].values/o0-1)*100)
        if extra:
            for k, v in extra.items():
                s[k] = v.values if isinstance(v, pd.Series) else v
        SIGS[key].append(s)

    last = {k: -99 for k in SIGS}
    for j in range(200, n - 1):
        e = min(j + 1 + NB, n)
        # A. Connors RSI(2)<5 + 200일선 위
        if C[j] > ma200[j] and r2[j] < 5 and j - last["A"] >= 3:
            push("A", j, dict(ex_ma5=(C[j+1:e] > ma5[j+1:e]), ex_r65=(r2[j+1:e] > 65))); last["A"] = j
        # B. RSI(2)<10
        if C[j] > ma200[j] and r2[j] < 10 and j - last["B"] >= 3:
            push("B", j, dict(ex_ma5=(C[j+1:e] > ma5[j+1:e]))); last["B"] = j
        # C. 볼린저 하단 + RSI14<30 반전
        if C[j-1] < bb_lo[j-1] and r14[j-1] < 30 and C[j] > bb_lo[j] and r14[j] > r14[j-1] and j - last["C"] >= MINGAP:
            push("C", j, dict(stop=(L[j-5:j+1].min()/O[j+1]-1)*100, ex_mid=(C[j+1:e] >= bb_m[j]))); last["C"] = j
        # D. 20EMA 눌림 + 양봉 (인도)
        if e20[j] > e50[j] and abs(C[j]/e20[j]-1) < 0.02 and C[j] > O[j] and C[j-1] <= e20[j-1]*1.02 and j - last["D"] >= MINGAP:
            push("D", j, dict(stop=(swlo[j]*0.98/O[j+1]-1)*100)); last["D"] = j
        # E. 20/50 EMA 골든크로스 (인도)
        if e20[j] > e50[j] and e20[j-1] <= e50[j-1] and j - last["E"] >= MINGAP:
            push("E", j, dict(ex_dc=(e20[j+1:e] < e50[j+1:e]))); last["E"] = j
        # F. 15일 박스 돌파 + 거래량 1.5배 (인도)
        if rng15[j-1] < 0.10 and C[j] > hi15[j-1] and V[j] >= 1.5 * v20[j-1] and j - last["F"] >= MINGAP:
            push("F", j, dict(stop=(hi15[j-1]*0.99/O[j+1]-1)*100)); last["F"] = j
        # G. 일본 25일선 상향돌파 + 거래량 + 고가갱신
        if C[j] > ma25[j] and C[j-1] <= ma25[j-1] and V[j] > v20[j-1] and H[j] >= hi20[j-1] and j - last["G"] >= MINGAP:
            push("G", j); last["G"] = j
        # H. 일본 25일선 눌림 (押し目買い)
        if ma25[j] > ma25[j-5] and C[j] > ma25[j] and L[j] <= ma25[j]*1.01 and C[j] > O[j] and j - last["H"] >= MINGAP:
            push("H", j); last["H"] = j
        # I. 중국 지호: 20일선 放量돌파 후 3일 유지 → 4일째 매수
        if (C[j-3] > ma20[j-3] and C[j-4] <= ma20[j-4] and V[j-3] >= 1.5 * v20[j-4]
            and all(C[j-k] > ma20[j-k] for k in range(3)) and j - last["I"] >= MINGAP):
            push("I", j, dict(ex_ma20=(C[j+1:e] < ma20[j+1:e]))); last["I"] = j
        # J. 단기 반전: 5일 -8%↓ + 200일선 위 (Quantpedia)
        if (C[j]/C[j-5]-1) < -0.08 and C[j] > ma200[j] and j - last["J"] >= 5:
            push("J", j); last["J"] = j

print("  ".join(f"{k}:{len(v):,}" for k, v in SIGS.items()))
def AMT(P, a=3): return [s for s in P if s["amt"] >= a]

show("A. Connors RSI(2)<5 + 200일선 위 (미국 대표 평균회귀)",
     [("청산: 종가>5일선 (원조)", A(AMT(SIGS["A"]), 20, exitkey="ex_ma5")),
      ("청산: RSI2>65", A(AMT(SIGS["A"]), 20, exitkey="ex_r65")),
      ("3일 고정", A(AMT(SIGS["A"]), 3)), ("5일 고정", A(AMT(SIGS["A"]), 5)), ("10일 고정", A(AMT(SIGS["A"]), 10)),
      ("+대금 50억 · 5일선 청산", A(AMT(SIGS["A"], 50), 20, exitkey="ex_ma5"))])
show("B. RSI(2)<10 완화판", [("5일선 청산", A(AMT(SIGS["B"]), 20, exitkey="ex_ma5")), ("5일 고정", A(AMT(SIGS["B"]), 5))])
show("C. 볼린저 하단 + RSI14<30 반전 (인도·미국 공통)",
     [("목표 중심선 청산", A(AMT(SIGS["C"]), 20, exitkey="ex_mid")), ("5일", A(AMT(SIGS["C"]), 5)), ("10일", A(AMT(SIGS["C"]), 10)),
      ("10일 · 저점 손절", A(AMT(SIGS["C"]), 10, stopkey="stop"))])
show("D. 20EMA 눌림 + 양봉 (인도 EMA pullback)",
     [("5일", A(AMT(SIGS["D"]), 5)), ("10일", A(AMT(SIGS["D"]), 10)), ("20일", A(AMT(SIGS["D"]), 20)),
      ("10일 · 스윙저점 -2% 손절", A(AMT(SIGS["D"]), 10, stopkey="stop"))])
show("E. 20/50 EMA 골든크로스 (인도)",
     [("데드크로스 청산", A(AMT(SIGS["E"]), 60, exitkey="ex_dc")), ("10일", A(AMT(SIGS["E"]), 10)), ("20일", A(AMT(SIGS["E"]), 20))])
show("F. 15일 박스 돌파 + 거래량 1.5배 (인도 breakout)",
     [("5일", A(AMT(SIGS["F"]), 5)), ("10일", A(AMT(SIGS["F"]), 10)),
      ("10일 · 박스 재진입 손절", A(AMT(SIGS["F"]), 10, stopkey="stop")), ("20일", A(AMT(SIGS["F"]), 20))])
show("G. 일본 25일선 상향돌파 + 거래량 + 고가갱신 (note.com 最強の型)",
     [("익절+7 손절-2", A(AMT(SIGS["G"]), 20, 2, 7)), ("익절+10 손절-3", A(AMT(SIGS["G"]), 20, 3, 10)),
      ("5일", A(AMT(SIGS["G"]), 5)), ("10일", A(AMT(SIGS["G"]), 10)), ("20일", A(AMT(SIGS["G"]), 20))])
show("H. 일본 25일선 押し目買い (눌림)",
     [("익절+7 손절-2", A(AMT(SIGS["H"]), 20, 2, 7)), ("5일", A(AMT(SIGS["H"]), 5)), ("10일", A(AMT(SIGS["H"]), 10)), ("20일", A(AMT(SIGS["H"]), 20))])
show("I. 중국 지호 波段: 20일선 放量돌파 + 3일 유지 후 매수",
     [("20일선 이탈 청산", A(AMT(SIGS["I"]), 60, exitkey="ex_ma20")), ("5일", A(AMT(SIGS["I"]), 5)), ("10일", A(AMT(SIGS["I"]), 10)), ("20일", A(AMT(SIGS["I"]), 20))])
show("J. 단기반전: 5일 -8%↓ + 200일선 위 (Quantpedia short-term reversal)",
     [("3일", A(AMT(SIGS["J"]), 3)), ("5일", A(AMT(SIGS["J"]), 5)), ("10일", A(AMT(SIGS["J"]), 10)), ("20일", A(AMT(SIGS["J"]), 20)),
      ("+대금 50억 · 5일", A(AMT(SIGS["J"], 50), 5))])
