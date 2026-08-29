# -*- coding: utf-8 -*-
"""새 데이터(공매도·공시)를 1·2번 필터에 접목 — 2019~2026"""
import io, pickle, sqlite3, sys
import numpy as np, pandas as pd
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
YS = list(range(2019, 2027))
S = [s for s in pickle.load(open("data/sig_2018.pkl", "rb")) if len(s["C"]) >= 2]

# ── 공매도: 신호일 기준 5일/20일 평균 공매도 비중, 그 변화
k = sqlite3.connect("file:data/kis/market.db?mode=ro", uri=True)
ss = pd.read_sql("SELECT date,ticker,short_ratio FROM short_sale WHERE short_ratio IS NOT NULL", k); k.close()
ss = ss.sort_values(["ticker", "date"])
g = ss.groupby("ticker")["short_ratio"]
ss["sr5"] = g.transform(lambda x: x.rolling(5).mean())
ss["sr20"] = g.transform(lambda x: x.rolling(20).mean())
ss["sr60"] = g.transform(lambda x: x.rolling(60).mean())
SR = {(r.date, r.ticker): (r.short_ratio, r.sr5, r.sr20, r.sr60) for r in ss.itertuples()}
print(f"공매도 지표 {len(SR):,}건")

# ── 공시: 신호일 이전 N일 내 유상증자/CB 여부
d = sqlite3.connect("file:data/dart/disclosures.db?mode=ro", uri=True)
dz = pd.read_sql("""SELECT stock_code, rcept_dt, report_nm FROM disclosure
   WHERE replace(report_nm,' ','') LIKE '%유상증자결정%'
      OR replace(report_nm,' ','') LIKE '%전환사채권발행결정%'
      OR replace(report_nm,' ','') LIKE '%신주인수권부사채권발행결정%'""", d)
dz2 = pd.read_sql("""SELECT stock_code, rcept_dt FROM disclosure
   WHERE replace(report_nm,' ','') LIKE '%자기주식취득결정%'
      OR replace(report_nm,' ','') LIKE '%주식소각%'""", d); d.close()
from collections import defaultdict
DIL = defaultdict(list); BUY = defaultdict(list)
for r in dz.itertuples(): DIL[r.stock_code].append(r.rcept_dt)
for r in dz2.itertuples(): BUY[r.stock_code].append(r.rcept_dt)
print(f"희석 공시 {len(dz):,}건 / 주주환원 공시 {len(dz2):,}건")

def recent(m, t, d, days):
    lo = (pd.Timestamp(d) - pd.Timedelta(days=days)).strftime("%Y%m%d")
    return any(lo <= x <= d for x in m.get(t, []))

for s in S:
    v = SR.get((s["d"], s["t"]))
    s["sr"], s["sr5"], s["sr20"], s["sr60"] = v if v else (None, None, None, None)
    s["dil90"] = recent(DIL, s["t"], s["d"], 90)
    s["buyback90"] = recent(BUY, s["t"], s["d"], 90)
print(f"공매도 결합된 신호: {sum(1 for s in S if s['sr5'] is not None):,}/{len(S):,}")

def cost(a):
    a = a or 3
    return 0.18 + (0.20 if a >= 100 else 0.30 if a >= 50 else 0.50 if a >= 20 else 0.70 if a >= 10 else 1.00)
def ev(s, h, sl, tp):
    H, L, C = s["H"], s["L"], s["C"]; n = min(h, len(C) - 1); c = cost(s["amt"])
    for i in range(n + 1):
        if sl and L[i] <= -sl: return -sl - c
        if tp and H[i] >= tp: return tp - c
        if i == n: return C[i] - c
def stat(P, h, sl, tp):
    if len(P) < 8: return None
    r = np.array([ev(s, h, sl, tp) for s in P]); w, l = r[r > 0], r[r <= 0]
    ys = {y: [ev(s, h, sl, tp) for s in P if s["y"] == y] for y in YS}
    npos = sum(1 for v in ys.values() if len(v) >= 3 and np.mean(v) > 0)
    ntot = sum(1 for v in ys.values() if len(v) >= 3)
    return dict(n=len(r), avg=r.mean(), med=np.median(r), win=len(w)/len(r)*100,
                pf=(w.sum()/abs(l.sum())) if len(l) else 99, pos=f"{npos}/{ntot}")
def show(t, rows):
    print(f"\n## {t}\n");print("| 추가 조건 | 건수 | 순수익 | 중앙값 | 승률 | PF | 플러스 연도 |\n|---|---|---|---|---|---|---|")
    for lab, a in rows:
        if not a: print(f"| {lab} | 부족 | - | - | - | - | - |"); continue
        print(f"| {lab} | {a['n']} | **{a['avg']:+.2f}%** | {a['med']:+.2f}% | {a['win']:.0f}% | {a['pf']:.2f} | {a['pos']} |")

F1 = lambda s: (s["quiet"]<0.5 and s["surge"]>=2 and s["fwp"]>=2 and s["amt"]>=50
                and 0<=s["ret10"]<=20 and s["k20"] and not s["pref"] and s["rs"] is not None and s["rs"]>0)
F2 = lambda s: (s["quiet"]<0.4 and s["surge"]>=2 and s["fwp"]>=2 and s["amt"]>=3
                and s["ret3"]<=0 and not s["pref"])
A1 = [s for s in S if F1(s)]; A2 = [s for s in S if F2(s)]
COND = [("없음(기준)", lambda s: True),
        ("공매도 비중 5일<20일 (감소)", lambda s: s["sr5"] is not None and s["sr20"] and s["sr5"] < s["sr20"]),
        ("공매도 비중 5일>20일 (증가)", lambda s: s["sr5"] is not None and s["sr20"] and s["sr5"] > s["sr20"]),
        ("공매도 비중 <3%", lambda s: s["sr5"] is not None and s["sr5"] < 3),
        ("공매도 비중 >5%", lambda s: s["sr5"] is not None and s["sr5"] > 5),
        ("공매도 20일<60일 (중기감소)", lambda s: s["sr20"] is not None and s["sr60"] and s["sr20"] < s["sr60"]),
        ("★유상증자·CB 90일내 제외", lambda s: not s["dil90"]),
        ("★자사주취득·소각 90일내", lambda s: s["buyback90"]),
        ("유상증자 제외 + 공매도 감소", lambda s: (not s["dil90"]) and s["sr5"] is not None and s["sr20"] and s["sr5"] < s["sr20"])]
show("1번 필터 (10일·손절15%·익절30%) · 기준 " + str(len(A1)) + "건",
     [(l, stat([s for s in A1 if f(s)], 10, 15, 30)) for l, f in COND])
show("2번 필터 (10일·손절10%) · 기준 " + str(len(A2)) + "건",
     [(l, stat([s for s in A2 if f(s)], 10, 10, None)) for l, f in COND])
