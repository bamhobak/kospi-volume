# -*- coding: utf-8 -*-
"""주간 거래량 3주 연속 +10%↑ 증가 신호 테스트 (절대수익 + 초과수익)"""
import io, pickle, sqlite3, sys
import numpy as np, pandas as pd
import FinanceDataReader as fdr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
YS = list(range(2019, 2027))
NB, MINGAP, GROW, NWEEK = 45, 15, 0.10, 3

con = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True)
df = pd.read_sql("""SELECT date,ticker,name,close,volume,frgn,open,high,low
                    FROM daily WHERE market='KOSPI' AND close IS NOT NULL ORDER BY ticker,date""", con)
dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily ORDER BY date")]; con.close()
POS = {d: i for i, d in enumerate(dates)}
df["wk"] = pd.to_datetime(df.date).dt.strftime("%G-%V")      # ISO 주차
ki = fdr.DataReader("KS11", "2017-12-01"); ki = ki[ki["Close"] > 0]
ki.index = ki.index.strftime("%Y%m%d")
KO, KC = ki["Open"].to_dict(), ki["Close"].to_dict()
K20 = (ki["Close"] > ki["Close"].rolling(20).mean()).to_dict()

SIG = []
for t, g in df.groupby("ticker", sort=False):
    if len(g) < 120: continue
    g = g.reset_index(drop=True)
    wv = g.groupby("wk")["volume"].sum()
    wend = g.groupby("wk")["date"].max()          # 각 주의 마지막 거래일
    wks = list(wv.index)
    grow = wv.pct_change()
    V = pd.Series(g["volume"].values, dtype="float64")
    F = pd.Series(g["frgn"].values, dtype="float64").fillna(0)
    Cs = pd.Series(g["close"].values, dtype="float64")
    v5 = V.rolling(5).sum(); fwp_s = (F.rolling(5).sum() / v5 * 100)
    amt_s = (V * Cs).rolling(20).mean() / 1e8
    ret10_s = (Cs / Cs.shift(10) - 1) * 100
    d2i = {d: i for i, d in enumerate(g["date"].values)}
    last = -99
    for wi in range(NWEEK, len(wks)):
        if not all(grow.iloc[wi - k] >= GROW for k in range(NWEEK)): continue
        d = wend.iloc[wi]                          # 신호 확정일 = 그 주 마지막 거래일
        j = d2i.get(d)
        if j is None or j + 1 >= len(g): continue
        if j - last < MINGAP: continue
        o0 = g["open"].values[j + 1]
        if o0 is None or not np.isfinite(o0) or o0 <= 0: continue
        e = min(j + 1 + NB, len(g))
        H, L, C = g["high"].values, g["low"].values, g["close"].values
        SIG.append(dict(t=t, d=d, y=int(d[:4]),
            H=(H[j+1:e]/o0-1)*100, L=(L[j+1:e]/o0-1)*100, C=(C[j+1:e]/o0-1)*100,
            grow=float(grow.iloc[wi]), grow3=float(wv.iloc[wi] / wv.iloc[wi-NWEEK] - 1),
            fwp=float(fwp_s.iloc[j]) if np.isfinite(fwp_s.iloc[j]) else 0.0,
            amt=float(amt_s.iloc[j]) if np.isfinite(amt_s.iloc[j]) else 0.0,
            ret10=float(ret10_s.iloc[j]) if np.isfinite(ret10_s.iloc[j]) else 0.0,
            k20=bool(K20.get(d, False)), pref=not t.endswith("0")))
        last = j
print(f"3주 연속 +{GROW*100:.0f}%↑ 신호: {len(SIG):,}건")
print("연도별:", {y: sum(1 for s in SIG if s['y'] == y) for y in YS})
pickle.dump(SIG, open("data/sig_weekly.pkl", "wb"))

def cost(a):
    a = a or 3
    return 0.18 + (0.20 if a >= 100 else 0.30 if a >= 50 else 0.50 if a >= 20 else 0.70 if a >= 10 else 1.00)
def ev2(s, h, sl, tp):
    H, L, C = s["H"], s["L"], s["C"]; n = min(h, len(C) - 1); c = cost(s["amt"])
    for i in range(n + 1):
        if sl and L[i] <= -sl: return -sl - c, i
        if tp and H[i] >= tp: return tp - c, i
        if i == n: return C[i] - c, i
def mkt(s, hh):
    p = POS.get(s["d"])
    if p is None or p + 1 + hh >= len(dates): return None
    o, c = KO.get(dates[p + 1]), KC.get(dates[p + 1 + hh])
    return None if not o or not c else (c / o - 1) * 100
def A(P, h, sl=None, tp=None):
    rows = []
    for s in P:
        r, hh = ev2(s, h, sl, tp); m = mkt(s, hh)
        if m is None: continue
        rows.append((s["y"], r, r - m))
    if len(rows) < 10: return None
    d = pd.DataFrame(rows, columns=["y", "ret", "al"])
    npos = sum(1 for y in YS if len(d[d.y == y]) >= 3 and d[d.y == y].al.mean() > 0)
    ntot = sum(1 for y in YS if len(d[d.y == y]) >= 3)
    return dict(n=len(d), ret=d.ret.mean(), al=d.al.mean(), win=(d.ret > 0).mean() * 100,
                alwin=(d.al > 0).mean() * 100, pos=f"{npos}/{ntot}")
def show(t, rows):
    print(f"\n## {t}\n");print("| 조건 | 건수 | 절대수익 | **초과수익** | 승률 | 초과승률 | 초과+ 연도 |\n|---|---|---|---|---|---|---|")
    for lab, a in rows:
        if not a: print(f"| {lab} | 부족 | - | - | - | - | - |"); continue
        print(f"| {lab} | {a['n']} | {a['ret']:+.2f}% | **{a['al']:+.2f}%** | {a['win']:.0f}% | {a['alwin']:.0f}% | {a['pos']} |")
show("보유기간별 (조건 없음)", [(f"{h}일", A(SIG, h)) for h in (5, 10, 15, 20, 30)])
base = [s for s in SIG if not s["pref"]]
show("추가 조건 (10일 보유)", [
    ("우선주 제외", A(base, 10)),
    ("+ 거래대금 3억↑", A([s for s in base if s["amt"] >= 3], 10)),
    ("+ 거래대금 50억↑", A([s for s in base if s["amt"] >= 50], 10)),
    ("+ 외국인 5일 순매수 >0", A([s for s in base if s["fwp"] > 0], 10)),
    ("+ 외국인 비중 2%↑", A([s for s in base if s["fwp"] >= 2], 10)),
    ("+ 코스피 20일선 위", A([s for s in base if s["k20"]], 10)),
    ("+ 3주 누적 증가 100%↑", A([s for s in base if s["grow3"] >= 1.0], 10)),
    ("대금3억+외인2%+지수20일선", A([s for s in base if s["amt"] >= 3 and s["fwp"] >= 2 and s["k20"]], 10)),
])
