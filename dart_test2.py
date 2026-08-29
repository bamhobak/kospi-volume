# -*- coding: utf-8 -*-
"""① 자사주신탁·무상증자 견고성 ② 악재 공시 제외를 1·2번 필터에 적용 ③ 재무 스냅샷(미래참조 경고)"""
import io, json, pickle, sqlite3, sys
from collections import defaultdict
import numpy as np, pandas as pd
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
exec(open("dart_test.py", encoding="utf-8").read().split("EVENTS = [")[0])   # 인프라 재사용

# ── ① 견고성
print("\n## ① 자사주 신탁 · 무상증자 — 거래대금 컷 (20일)\n")
print("| 이벤트 | 대금 | 건수 | 초과수익 | 초과중앙값 | 초과승률 | 초과+ 연도 |\n|---|---|---|---|---|---|---|")
for lab, pat in (("자사주 취득 신탁", "자기주식취득신탁계약체결"), ("무상증자", "무상증자결정")):
    allS = signals(pat)
    for a in (3, 10, 30, 50):
        r = A([s for s in allS if s["amt"] >= a], 20)
        if r: print(f"| {lab} | {a}억↑ | {r['n']} | **{r['al']:+.2f}%** | {r['med']:+.2f}% | {r['alwin']:.0f}% | {r['pos']} |")

# ── ② 악재 공시 제외 → 1·2번 필터
S = [s for s in pickle.load(open("data/sig_2018.pkl", "rb")) if len(s["C"]) >= 2]
BAD = {"최대주주변경": "최대주주변경(?!.*신고)", "자기주식처분": "자기주식처분결정", "불성실공시": "불성실공시",
       "타법인취득": "타법인주식및출자증권취득결정", "회사합병": "회사합병결정", "유상증자": "유상증자결정",
       "전환사채": "전환사채권발행결정"}
GOOD = {"자사주신탁": "자기주식취득신탁계약체결", "자사주취득": "자기주식취득결정"}
EV = defaultdict(lambda: defaultdict(list))
for k, pat in {**BAD, **GOOD}.items():
    for r in disc[disc.nm.str.contains(pat, na=False, regex=True)].itertuples():
        EV[k][r.ticker].append(r.rcept_dt)
def had(k, t, d, days=90):
    lo = (pd.Timestamp(d) - pd.Timedelta(days=days)).strftime("%Y%m%d")
    return any(lo <= x <= d for x in EV[k].get(t, []))
k = sqlite3.connect("file:data/kis/market.db?mode=ro", uri=True)
ss = pd.read_sql("SELECT date,ticker,short_ratio FROM short_sale WHERE short_ratio IS NOT NULL", k); k.close()
ss = ss.sort_values(["ticker", "date"]); gg = ss.groupby("ticker")["short_ratio"]
ss["sr5"] = gg.transform(lambda x: x.rolling(5).mean()); ss["sr20"] = gg.transform(lambda x: x.rolling(20).mean())
SR = {(r.date, r.ticker): (r.sr5, r.sr20) for r in ss.itertuples()}
for s in S:
    v = SR.get((s["d"], s["t"])); s["srdown"] = bool(v and v[0] is not None and v[1] and v[0] < v[1])
    for kk in list(BAD) + list(GOOD): s[kk] = had(kk, s["t"], s["d"])
F1 = lambda s: (s["quiet"] < 0.5 and s["surge"] >= 2 and s["fwp"] >= 2 and s["amt"] >= 50 and 0 <= s["ret10"] <= 20
                and s["k20"] and not s["pref"] and s["rs"] is not None and s["rs"] > 0)
F2 = lambda s: (s["quiet"] < 0.3 and s["surge"] >= 2 and s["fwp"] >= 2 and s["amt"] >= 3 and s["ret3"] <= 0
                and not s["pref"] and s["srdown"] and not s["유상증자"] and not s["전환사채"])
def cost(a):
    a = a or 3
    return 0.18 + (0.20 if a >= 100 else 0.30 if a >= 50 else 0.50 if a >= 20 else 0.70 if a >= 10 else 1.00)
def evf(s, h, sl, tp):
    H, L, C = s["H"], s["L"], s["C"]; n = min(h, len(C) - 1); c = cost(s["amt"])
    for i in range(n + 1):
        if sl and L[i] <= -sl: return -sl - c, i
        if tp and H[i] >= tp: return tp - c, i
        if i == n: return C[i] - c, i
def AF(P, h, sl, tp, mn=15):
    rows = []
    for s in P:
        r, hh = evf(s, h, sl, tp); m = mkt(s, hh)
        if m is None: continue
        rows.append((s["y"], r, r - m))
    if len(rows) < mn: return None
    dd = pd.DataFrame(rows, columns=["y", "ret", "al"])
    yy = dd.groupby("y").al.mean(); cnt = dd.groupby("y").size(); ok = yy[cnt >= 3]
    return dict(n=len(dd), al=dd.al.mean(), med=dd.al.median(), win=(dd.ret > 0).mean() * 100, pos=f"{(ok>0).sum()}/{len(ok)}")
A1 = [s for s in S if F1(s)]; A2 = [s for s in S if F2(s)]
print("\n## ② 악재 공시(90일 내) 제외 효과\n")
print("| 필터 | 제외 조건 | 건수 | 초과수익 | 초과중앙값 | 승률 | 초과+ 연도 |\n|---|---|---|---|---|---|---|")
for lab, P, h, sl, tp in (("1번", A1, 10, 15, 30), ("2번", A2, 10, None, None)):
    base = AF(P, h, sl, tp)
    print(f"| {lab} | 없음(현재) | {base['n']} | **{base['al']:+.2f}%** | {base['med']:+.2f}% | {base['win']:.0f}% | {base['pos']} |")
    for k in ("최대주주변경", "자기주식처분", "불성실공시", "타법인취득", "회사합병"):
        r = AF([s for s in P if not s[k]], h, sl, tp)
        cut = len(P) - (r["n"] if r else 0)
        if r: print(f"| {lab} | {k} 제외 (-{sum(1 for s in P if s[k])}건) | {r['n']} | **{r['al']:+.2f}%** | {r['med']:+.2f}% | {r['win']:.0f}% | {r['pos']} |")
    allbad = [s for s in P if not any(s[k] for k in ("최대주주변경", "자기주식처분", "불성실공시", "타법인취득", "회사합병"))]
    r = AF(allbad, h, sl, tp)
    if r: print(f"| {lab} | **5개 전부 제외** (-{len(P)-len(allbad)}건) | {r['n']} | **{r['al']:+.2f}%** | {r['med']:+.2f}% | {r['win']:.0f}% | {r['pos']} |")
    for k in ("자사주신탁", "자사주취득"):
        r = AF([s for s in P if s[k]], h, sl, tp, mn=8)
        print(f"| {lab} | {k} 있는 것만 | {r['n'] if r else sum(1 for s in P if s[k])} | " + (f"**{r['al']:+.2f}%** | {r['med']:+.2f}% | {r['win']:.0f}% | {r['pos']} |" if r else "부족 | | | |"))

# ── ③ 재무 스냅샷 (⚠ 2026-08-29 현재값 → 과거 신호에 적용 = 미래참조. 참고용)
fund = json.load(open("data/fundamental/20260829.json", encoding="utf-8"))["stocks"]
def q(t, item):
    x = fund.get(t)
    if not x: return None
    it = ((x.get("quarter") or {}).get("items") or {}).get(item) or {}
    v = [v for k, v in sorted(it.items()) if v is not None]
    return v[-1] if v else None
for s in S:
    s["op"] = q(s["t"], "op"); s["debt"] = q(s["t"], "debt"); s["pbr"] = (fund.get(s["t"]) or {}).get("pbr")
print("\n## ③ 재무 스냅샷 적용 (⚠ 현재 재무를 과거에 적용 = 미래참조 오염, 방향 참고만)\n")
print("| 필터 | 조건 | 건수 | 초과수익 | 승률 | 초과+ 연도 |\n|---|---|---|---|---|---|")
for lab, P, h, sl, tp in (("1번", A1, 10, 15, 30), ("2번", A2, 10, None, None)):
    for cl, fn in (("기준", lambda s: True), ("영업적자 제외", lambda s: s["op"] is None or s["op"] >= 0),
                   ("부채비율<200", lambda s: s["debt"] is None or s["debt"] < 200), ("PBR<1", lambda s: s["pbr"] is not None and s["pbr"] < 1),
                   ("PBR>=1", lambda s: s["pbr"] is not None and s["pbr"] >= 1)):
        r = AF([s for s in P if fn(s)], h, sl, tp, mn=10)
        if r: print(f"| {lab} | {cl} | {r['n']} | **{r['al']:+.2f}%** | {r['win']:.0f}% | {r['pos']} |")
