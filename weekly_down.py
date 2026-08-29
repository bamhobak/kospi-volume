# -*- coding: utf-8 -*-
"""주간 거래량 3주 연속 -10%↑ 감소 신호 테스트 (절대수익 + 초과수익)"""
import io, pickle, sqlite3, sys
import numpy as np, pandas as pd
import FinanceDataReader as fdr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
YS = list(range(2019, 2027))
NB, MINGAP = 45, 15

con = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True)
df = pd.read_sql("""SELECT date,ticker,close,volume,frgn,open,high,low
                    FROM daily WHERE market='KOSPI' AND close IS NOT NULL ORDER BY ticker,date""", con)
dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily ORDER BY date")]; con.close()
POS = {d: i for i, d in enumerate(dates)}
df["wk"] = pd.to_datetime(df.date).dt.strftime("%G-%V")
ki = fdr.DataReader("KS11", "2017-12-01"); ki = ki[ki["Close"] > 0]
ki.index = ki.index.strftime("%Y%m%d")
KO, KC = ki["Open"].to_dict(), ki["Close"].to_dict()
K20 = (ki["Close"] > ki["Close"].rolling(20).mean()).to_dict()

SIG = []
for t, g in df.groupby("ticker", sort=False):
    if len(g) < 300: continue
    g = g.reset_index(drop=True)
    wv = g.groupby("wk")["volume"].sum()
    wend = g.groupby("wk")["date"].max()
    grow = wv.pct_change()
    V = pd.Series(g["volume"].values, dtype="float64"); Cs = pd.Series(g["close"].values, dtype="float64")
    F = pd.Series(g["frgn"].values, dtype="float64").fillna(0)
    v5 = V.rolling(5).sum(); fwp_s = (F.rolling(5).sum() / v5 * 100)
    amt_s = (V * Cs).rolling(20).mean() / 1e8
    q_s = V.rolling(40).mean() / V.shift(40).rolling(200).mean()      # 잠잠도
    ret10_s = (Cs / Cs.shift(10) - 1) * 100
    ret20_s = (Cs / Cs.shift(20) - 1) * 100
    d2i = {d: i for i, d in enumerate(g["date"].values)}
    H, L, C, O = g["high"].values, g["low"].values, g["close"].values, g["open"].values
    last = -99
    for wi in range(3, len(wv)):
        if not all(grow.iloc[wi - k] <= -0.10 for k in range(3)): continue
        d = wend.iloc[wi]; j = d2i.get(d)
        if j is None or j + 1 >= len(g) or j - last < MINGAP: continue
        o0 = O[j + 1]
        if o0 is None or not np.isfinite(o0) or o0 <= 0: continue
        e = min(j + 1 + NB, len(g))
        gv = lambda s_: float(s_.iloc[j]) if np.isfinite(s_.iloc[j]) else 0.0
        SIG.append(dict(t=t, d=d, y=int(d[:4]),
            H=(H[j+1:e]/o0-1)*100, L=(L[j+1:e]/o0-1)*100, C=(C[j+1:e]/o0-1)*100,
            drop3=float(wv.iloc[wi] / wv.iloc[wi-3] - 1),
            fwp=gv(fwp_s), amt=gv(amt_s), quiet=gv(q_s),
            ret10=gv(ret10_s), ret20=gv(ret20_s),
            k20=bool(K20.get(d, False)), pref=not t.endswith("0")))
        last = j
print(f"3주 연속 -10%↑ 감소 신호: {len(SIG):,}건")
print("연도별:", {y: sum(1 for s in SIG if s['y'] == y) for y in YS})

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
                alwin=(d.al > 0).mean() * 100, med=d.al.median(), pos=f"{npos}/{ntot}")
def show(t, rows):
    print(f"\n## {t}\n");print("| 조건 | 건수 | 절대수익 | **초과수익** | 초과 중앙값 | 승률 | 초과승률 | 초과+ 연도 |\n|---|---|---|---|---|---|---|---|")
    for lab, a in rows:
        if not a: print(f"| {lab} | 부족 | - | - | - | - | - | - |"); continue
        print(f"| {lab} | {a['n']} | {a['ret']:+.2f}% | **{a['al']:+.2f}%** | {a['med']:+.2f}% | {a['win']:.0f}% | {a['alwin']:.0f}% | {a['pos']} |")
show("보유기간별", [(f"{h}일", A(SIG, h)) for h in (5, 10, 15, 20, 30, 40)])
b = [s for s in SIG if not s["pref"]]
show("추가 조건 (20일 보유)", [
    ("우선주 제외", A(b, 20)),
    ("+ 거래대금 3억↑", A([s for s in b if s["amt"] >= 3], 20)),
    ("+ 거래대금 50억↑", A([s for s in b if s["amt"] >= 50], 20)),
    ("+ 외국인 순매수 >0", A([s for s in b if s["fwp"] > 0], 20)),
    ("+ 외국인 비중 2%↑", A([s for s in b if s["fwp"] >= 2], 20)),
    ("+ 코스피 20일선 위", A([s for s in b if s["k20"]], 20)),
    ("+ 잠잠도 <0.5", A([s for s in b if 0 < s["quiet"] < 0.5], 20)),
    ("+ 20일 주가 하락", A([s for s in b if s["ret20"] <= 0], 20)),
    ("+ 20일 주가 상승", A([s for s in b if s["ret20"] > 0], 20)),
    ("+ 3주 누적 -50%↓", A([s for s in b if s["drop3"] <= -0.5], 20)),
])
