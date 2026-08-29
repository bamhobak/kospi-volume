# -*- coding: utf-8 -*-
"""1·2번 필터 파라미터 스윕 — 지수 대비 초과수익 기준"""
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
ki.index = ki.index.strftime("%Y%m%d"); KO, KC = ki["Open"].to_dict(), ki["Close"].to_dict()
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
def A(P, h, sl=None, tp=None, mn=20):
    rows = []
    for s in P:
        r, hh = ev2(s, h, sl, tp); m = mkt(s, hh)
        if m is None: continue
        rows.append((s["y"], r, r - m))
    if len(rows) < mn: return None
    d = pd.DataFrame(rows, columns=["y", "ret", "al"])
    yy = d.groupby("y").al.mean(); cnt = d.groupby("y").size()
    ok = yy[cnt >= 3]
    return dict(n=len(d), ret=d.ret.mean(), al=d.al.mean(), med=d.al.median(),
                win=(d.ret > 0).mean() * 100, alwin=(d.al > 0).mean() * 100,
                pos=f"{(ok>0).sum()}/{len(ok)}")
def show(t, rows):
    print(f"\n## {t}\n");print("| 설정 | 건수 | 절대수익 | **초과수익** | 초과중앙값 | 승률 | 초과승률 | 초과+ 연도 |\n|---|---|---|---|---|---|---|---|")
    for lab, a in rows:
        if not a: print(f"| {lab} | 부족 |" + " - |" * 6); continue
        print(f"| {lab} | {a['n']} | {a['ret']:+.2f}% | **{a['al']:+.2f}%** | {a['med']:+.2f}% | {a['win']:.0f}% | {a['alwin']:.0f}% | {a['pos']} |")

B1 = lambda s, fw=2, q=0.5, am=50, sg=2: (s["quiet"]<q and s["surge"]>=sg and s["fwp"]>=fw and s["amt"]>=am
      and 0<=s["ret10"]<=20 and s["k20"] and not s["pref"] and s["rs"] is not None and s["rs"]>0)
B2 = lambda s, fw=2, q=0.4, am=3, sg=2: (s["quiet"]<q and s["surge"]>=sg and s["fwp"]>=fw and s["amt"]>=am
      and s["ret3"]<=0 and not s["pref"])
print("# 1번 필터 (기준: 외인2%·잠잠<0.5·대금50억·급등2배 · 10일·손절15%·익절30%)")
show("① 외국인 비중 임계값", [(f"외인 {v}%↑", A([s for s in S if B1(s, fw=v)], 10, 15, 30)) for v in (0,1,2,3,5,7,10)])
show("② 잠잠도 상한", [(f"잠잠 <{v}", A([s for s in S if B1(s, q=v)], 10, 15, 30)) for v in (0.3,0.4,0.5,0.6,0.7)])
show("③ 급등 배율", [(f"급등 {v}배↑", A([s for s in S if B1(s, sg=v)], 10, 15, 30)) for v in (2,2.5,3,4)])
show("④ 거래대금 하한", [(f"{v}억↑", A([s for s in S if B1(s, am=v)], 10, 15, 30)) for v in (3,10,30,50,100,200)])
A1 = [s for s in S if B1(s)]
show("⑤ 보유기간 (손절15%·익절30% 유지)", [(f"{h}일", A(A1, h, 15, 30)) for h in (3,5,10,15,20,40,60)])
show("⑥ 보유기간 (손절·익절 없음)", [(f"{h}일", A(A1, h)) for h in (3,5,10,15,20,40,60)])
show("⑦ 손절/익절 (10일)", [("없음", A(A1,10)), ("손절10%", A(A1,10,10)), ("손절15%", A(A1,10,15)),
                        ("손절20%", A(A1,10,20)), ("익절20%", A(A1,10,None,20)), ("익절30%", A(A1,10,None,30)),
                        ("손절15+익절30", A(A1,10,15,30))])
print("\n\n# 2번 필터 (기준: 외인2%·잠잠<0.4·대금3억·급등2배 · 10일·손절10%)")
show("① 외국인 비중", [(f"외인 {v}%↑", A([s for s in S if B2(s, fw=v)], 10, 10)) for v in (0,1,2,3,5,7,10)])
show("② 잠잠도 상한", [(f"잠잠 <{v}", A([s for s in S if B2(s, q=v)], 10, 10)) for v in (0.2,0.3,0.4,0.5,0.6,0.7)])
show("③ 급등 배율", [(f"급등 {v}배↑", A([s for s in S if B2(s, sg=v)], 10, 10)) for v in (2,2.5,3,4)])
show("④ 거래대금 하한", [(f"{v}억↑", A([s for s in S if B2(s, am=v)], 10, 10)) for v in (3,10,30,50,100)])
A2 = [s for s in S if B2(s)]
show("⑤ 보유기간 (손절10% 유지)", [(f"{h}일", A(A2, h, 10)) for h in (3,5,10,15,20,40,60)])
show("⑥ 보유기간 (손절 없음)", [(f"{h}일", A(A2, h)) for h in (3,5,10,15,20,40,60)])
