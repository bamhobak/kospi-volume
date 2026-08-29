# -*- coding: utf-8 -*-
"""6개월 잠잠 → 주간 거래량 연속 증가 + 외국인 비중 증가 신호 검증"""
import io, pickle, sqlite3, sys
import numpy as np, pandas as pd
import FinanceDataReader as fdr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
NB, MINGAP = 70, 15
con = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True)
df = pd.read_sql("""SELECT date,ticker,name,close,volume,frgn,open,high,low FROM daily
   WHERE market='KOSPI' AND close IS NOT NULL AND open>0 ORDER BY ticker,date""", con)
dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily ORDER BY date")]; con.close()
POS = {d: i for i, d in enumerate(dates)}
df["wk"] = pd.to_datetime(df.date).dt.strftime("%G-%V")
ki = fdr.DataReader("KS11", "2017-12-01"); ki = ki[ki.Close > 0]; ki.index = ki.index.strftime("%Y%m%d")
KO, KC = ki["Open"].to_dict(), ki["Close"].to_dict()
K20 = (ki["Close"] > ki["Close"].rolling(20).mean()).to_dict()

SIG = []
for t, g in df.groupby("ticker", sort=False):
    if len(g) < 400: continue
    g = g.reset_index(drop=True)
    V = pd.Series(g["volume"].values, dtype="float64")
    F = pd.Series(g["frgn"].values, dtype="float64").fillna(0)
    Cs = pd.Series(g["close"].values, dtype="float64")
    # 잠잠: 최근 6개월(120일) 평균 < 그 이전 1년(240일) 평균의 50%
    q6 = V.rolling(120).mean() / V.shift(120).rolling(240).mean()
    amt = (V * Cs).rolling(20).mean() / 1e8
    # 주간 집계
    wv = g.groupby("wk")["volume"].sum()
    wf = g.groupby("wk")["frgn"].sum()
    wend = g.groupby("wk")["date"].max()
    grow = wv.pct_change()
    fwr = (wf / wv * 100)                       # 주간 외국인 순매수 비중
    d2i = {d: i for i, d in enumerate(g["date"].values)}
    H, L, C, O = g["high"].values, g["low"].values, g["close"].values, g["open"].values
    last = -99
    for wi in range(4, len(wv)):
        d = wend.iloc[wi]; j = d2i.get(d)
        if j is None or j + 1 >= len(g) or j - last < MINGAP: continue
        if not np.isfinite(q6.iloc[j]) or q6.iloc[j] >= 0.5: continue      # 6개월 잠잠
        up2 = grow.iloc[wi] >= 0.10 and grow.iloc[wi-1] >= 0.10
        up3 = up2 and grow.iloc[wi-2] >= 0.10
        if not up2: continue
        o0 = O[j + 1]
        if not np.isfinite(o0) or o0 <= 0: continue
        e = min(j + 1 + NB, len(g))
        f_now = fwr.iloc[wi-1:wi+1].mean()        # 최근 2주 외국인 비중
        f_prev = fwr.iloc[wi-5:wi-1].mean()       # 직전 4주
        SIG.append(dict(t=t, n=g["name"].iloc[-1], d=d, y=int(d[:4]),
            H=(H[j+1:e]/o0-1)*100, L=(L[j+1:e]/o0-1)*100, C=(C[j+1:e]/o0-1)*100,
            q6=float(q6.iloc[j]), up3=bool(up3), amt=float(amt.iloc[j]) if np.isfinite(amt.iloc[j]) else 0.0,
            fnow=float(f_now) if np.isfinite(f_now) else 0.0,
            fup=bool(np.isfinite(f_now) and np.isfinite(f_prev) and f_now > f_prev),
            grow3=float(wv.iloc[wi]/wv.iloc[wi-3]-1) if wv.iloc[wi-3] > 0 else 0.0,
            k20=bool(K20.get(d, False)), pref=not t.endswith("0")))
        last = j
print(f"신호 {len(SIG):,}건 · 연도별:", {y: sum(1 for s in SIG if s['y']==y) for y in range(2019,2027)})
pickle.dump(SIG, open("data/sig_quietramp.pkl", "wb"))
def cost(a):
    a = a or 3
    return 0.18 + (0.20 if a >= 100 else 0.30 if a >= 50 else 0.50 if a >= 20 else 0.70 if a >= 10 else 1.00)
def ev2(s, h, sl=None, tp=None):
    H, L, C = s["H"], s["L"], s["C"]; n = min(h, len(C)-1); c = cost(s["amt"])
    for i in range(n+1):
        if sl and L[i] <= -sl: return -sl-c, i
        if tp and H[i] >= tp: return tp-c, i
        if i == n: return C[i]-c, i
def mkt(s, hh):
    p = POS.get(s["d"])
    if p is None or p+1+hh >= len(dates): return None
    o, c = KO.get(dates[p+1]), KC.get(dates[p+1+hh])
    return None if not o or not c else (c/o-1)*100
def A(P, h, sl=None, tp=None, mn=15):
    rows = []
    for s in P:
        r, hh = ev2(s, h, sl, tp); m = mkt(s, hh)
        if m is None: continue
        rows.append((s["y"], r, r-m))
    if len(rows) < mn: return None
    d = pd.DataFrame(rows, columns=["y","ret","al"])
    yy = d.groupby("y").al.mean(); cnt = d.groupby("y").size(); ok = yy[cnt>=3]
    return dict(n=len(d), ret=d.ret.mean(), al=d.al.mean(), med=d.al.median(),
                win=(d.ret>0).mean()*100, alwin=(d.al>0).mean()*100, pos=f"{(ok>0).sum()}/{len(ok)}")
def show(t, rows):
    print(f"\n## {t}\n");print("| 설정 | 건수 | 절대수익 | **초과수익** | 초과중앙값 | 승률 | 초과승률 | 초과+ 연도 |\n|---|---|---|---|---|---|---|---|")
    for lab, a in rows:
        if not a: print(f"| {lab} | 부족 |"+" - |"*6); continue
        print(f"| {lab} | {a['n']} | {a['ret']:+.2f}% | **{a['al']:+.2f}%** | {a['med']:+.2f}% | {a['win']:.0f}% | {a['alwin']:.0f}% | {a['pos']} |")
B = [s for s in SIG if not s["pref"] and s["amt"] >= 3]
show("① 기본형 (2주 연속 +10%) · 보유기간별", [(f"{h}일", A(B, h)) for h in (3,5,10,15,20,40,60)])
B3 = [s for s in B if s["up3"]]
show("② 3주 연속 +10% · 보유기간별", [(f"{h}일", A(B3, h)) for h in (3,5,10,15,20,40,60)])
show("③ 외국인 조건 (2주 연속 · 20일 보유)",
     [("조건 없음", A(B, 20)), ("외국인 비중 증가", A([s for s in B if s["fup"]], 20)),
      ("외국인 비중 >0", A([s for s in B if s["fnow"] > 0], 20)),
      ("증가 + >0", A([s for s in B if s["fup"] and s["fnow"] > 0], 20)),
      ("증가 + >2%", A([s for s in B if s["fup"] and s["fnow"] >= 2], 20))])
show("④ 3주 연속 + 외국인 증가 · 보유기간별",
     [(f"{h}일", A([s for s in B3 if s["fup"] and s["fnow"] > 0], h)) for h in (5,10,15,20,40,60)])
BEST = [s for s in B if s["fup"] and s["fnow"] > 0]
show("⑤ 2주+외국인증가 · 추가 조건 (20일)",
     [("기본", A(BEST, 20)), ("+대금 10억↑", A([s for s in BEST if s["amt"]>=10], 20)),
      ("+대금 50억↑", A([s for s in BEST if s["amt"]>=50], 20)),
      ("+코스피 20일선 위", A([s for s in BEST if s["k20"]], 20)),
      ("+잠잠 <0.3", A([s for s in BEST if s["q6"]<0.3], 20))])
