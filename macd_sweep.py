"""전략2(추세반전) 개선 스윕: 손익비·트레일링·추세필터·시장필터·지연 조건
python macd_sweep.py
"""
import io, sys, pickle, itertools
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
PIVOT, MAXLAG = 5, 20
cache = pickle.load(open(BASE / "data" / "macd_ohlc.pkl", "rb"))
kospi = fdr.DataReader("KS11", "2022-06-01", "2026-08-28")
kospi["ma5"] = kospi["Close"].rolling(5).mean(); kospi["ma20"] = kospi["Close"].rolling(20).mean()
kup5 = {d: bool(r["Close"] > r["ma5"]) for d, r in kospi.iterrows()}
kup20 = {d: bool(r["Close"] > r["ma20"]) for d, r in kospi.iterrows()}

def prep(d):
    d = d.copy()
    d["macd"] = d["Close"].ewm(span=12, adjust=False).mean() - d["Close"].ewm(span=26, adjust=False).mean()
    d["sig"] = d["macd"].ewm(span=9, adjust=False).mean()
    d["ma200"] = d["Close"].rolling(200).mean()
    d["ma20"] = d["Close"].rolling(20).mean()
    return d

def swings(a_hi, a_lo, L=PIVOT):
    hi, lo = [], []
    for i in range(L, len(a_hi) - L):
        if a_hi[i] == max(a_hi[i - L:i + L + 1]): hi.append((i + L, i, a_hi[i]))
        if a_lo[i] == min(a_lo[i - L:i + L + 1]): lo.append((i + L, i, a_lo[i]))
    return hi, lo

def line(p, x):
    (x1, y1), (x2, y2) = p
    return y1 + (y2 - y1) * (x - x1) / max(1, (x2 - x1))

# ---------- 신호 수집 (롱만) ----------
sigs = []
for code, d0 in cache.items():
    if d0 is None or len(d0) < 320: continue
    d = prep(d0)
    H, L, C, M, MA200, MA20 = d["High"].values, d["Low"].values, d["Close"].values, d["macd"].values, d["ma200"].values, d["ma20"].values
    sw_hi, sw_lo = swings(H, L); mh, _ = swings(M, M)
    dates = d.index
    start = np.searchsorted(dates, pd.Timestamp("2023-01-01"))
    last = -99
    for i in range(max(start, 210), len(d) - 1):
        if i - last < 5: continue
        ph = [(j, v) for (t, j, v) in sw_hi if t <= i][-2:]
        mhi = [(j, v) for (t, j, v) in mh if t <= i][-2:]
        if len(ph) < 2 or len(mhi) < 2 or ph[1][1] >= ph[0][1] or mhi[1][1] >= mhi[0][1]: continue
        mbreak = None
        for k in range(max(mhi[1][0] + 1, i - MAXLAG), i + 1):
            if M[k] > line(mhi, k): mbreak = k; break
        if mbreak is None or mbreak >= i: continue
        if not (C[i] > line(ph, i) and C[i - 1] <= line(ph, i - 1)): continue
        stop = min(L[mbreak:i + 1]); o = d["Open"].iloc[i + 1]
        if not (o > stop > 0): continue
        last = i
        sigs.append(dict(code=code, i=i + 1, date=dates[i], o=o, stop=stop,
                         risk=(o - stop) / o * 100, lag=i - mbreak,
                         above200=bool(C[i] > MA200[i]) if not np.isnan(MA200[i]) else False,
                         above20=bool(C[i] > MA20[i]) if not np.isnan(MA20[i]) else False,
                         k5=kup5.get(dates[i], False), k20=kup20.get(dates[i], False),
                         y=dates[i].year))
print(f"롱 신호 {len(sigs)}건", file=sys.stderr)
prepped = {c: prep(d) for c, d in cache.items() if d is not None and len(d) >= 320}

def run(s, rr=None, trail=None, maxbars=40, be=False):
    """be: 목표 절반 도달 시 손절을 본전으로"""
    d = prepped[s["code"]]; i0, o, stop = s["i"], s["o"], s["stop"]
    if i0 >= len(d): return None
    tgt = o + rr * (o - stop) if rr else None
    half = o + 0.5 * (o - stop) * (rr or 2)
    hi = o; st = stop
    for k in range(i0, min(i0 + maxbars, len(d))):
        lo_, hi_ = d["Low"].iloc[k], d["High"].iloc[k]
        if trail and hi > o and lo_ <= hi * (1 - trail / 100): return (hi * (1 - trail / 100) / o - 1) * 100
        if lo_ <= st: return (st / o - 1) * 100
        if tgt and hi_ >= tgt: return (tgt / o - 1) * 100
        if be and hi_ >= half: st = max(st, o)
        hi = max(hi, hi_)
    j = min(i0 + maxbars, len(d)) - 1
    return (d["Close"].iloc[j] / o - 1) * 100

def stat(rows):
    r = [x for x in rows if x is not None]
    if len(r) < 20: return None
    return dict(n=len(r), avg=np.mean(r), win=np.mean([v > 0 for v in r]) * 100, med=np.median(r),
                pf=(sum(v for v in r if v > 0) / abs(sum(v for v in r if v < 0))) if any(v < 0 for v in r) else 99)
def fmt(s): return f"{s['avg']:+.2f}% / {s['win']:.0f}% / PF {s['pf']:.2f} ({s['n']})" if s else "표본부족"

IS = [s for s in sigs if s["y"] <= 2024]; OOS = [s for s in sigs if s["y"] >= 2025]
print("# 전략2(추세반전·롱) 개선 스윕\n")
print("표기: 평균 / 승률 / PF(총이익÷총손실) (건수) · IS=2023~24, OOS=2025~26\n")

print("## 1) 청산 규칙\n\n| 규칙 | 전체 | IS(2023~24) | OOS(2025~26) |\n|---|---|---|---|")
rules = [("손익비 1:1.5", dict(rr=1.5)), ("손익비 1:2 (기준)", dict(rr=2)), ("손익비 1:3", dict(rr=3)), ("손익비 1:4", dict(rr=4)),
         ("트레일링 8%", dict(trail=8)), ("트레일링 10%", dict(trail=10)), ("트레일링 15%", dict(trail=15)),
         ("1:3 + 본전스톱", dict(rr=3, be=True)), ("1:2 + 60봉", dict(rr=2, maxbars=60)), ("1:3 + 트레일12%", dict(rr=3, trail=12))]
best = None
for lab, kw in rules:
    a, b, c = stat([run(s, **kw) for s in sigs]), stat([run(s, **kw) for s in IS]), stat([run(s, **kw) for s in OOS])
    print(f"| {lab} | {fmt(a)} | {fmt(b)} | {fmt(c)} |")

print("\n## 2) 필터 (손익비 1:3 고정)\n\n| 필터 | 전체 | IS | OOS |\n|---|---|---|---|")
filts = [("없음", lambda s: True), ("종가>200일선", lambda s: s["above200"]), ("종가>20일선", lambda s: s["above20"]),
         ("코스피>5일선", lambda s: s["k5"]), ("코스피>20일선", lambda s: s["k20"]),
         ("200일선 위 + 코스피>20일선", lambda s: s["above200"] and s["k20"]),
         ("손절폭 ≤5%", lambda s: s["risk"] <= 5), ("손절폭 ≤8%", lambda s: s["risk"] <= 8), ("손절폭 ≥10%", lambda s: s["risk"] >= 10),
         ("MACD선행 3봉 이내", lambda s: s["lag"] <= 3), ("MACD선행 4~10봉", lambda s: 4 <= s["lag"] <= 10)]
for lab, f in filts:
    S = [s for s in sigs if f(s)]
    a, b, c = stat([run(s, rr=3) for s in S]), stat([run(s, rr=3) for s in S if s["y"] <= 2024]), stat([run(s, rr=3) for s in S if s["y"] >= 2025])
    print(f"| {lab} | {fmt(a)} | {fmt(b)} | {fmt(c)} |")

print("\n## 3) 조합 상위 (OOS 기준 정렬)\n\n| 필터 | 청산 | 전체 | IS | OOS |\n|---|---|---|---|---|")
combos = []
for flab, f in filts:
    S = [s for s in sigs if f(s)]
    for rlab, kw in rules:
        c = stat([run(s, **kw) for s in S if s["y"] >= 2025])
        if not c: continue
        a = stat([run(s, **kw) for s in S]); b = stat([run(s, **kw) for s in S if s["y"] <= 2024])
        if b and b["avg"] > 0: combos.append((c["avg"], flab, rlab, a, b, c))
combos.sort(reverse=True, key=lambda x: x[0])
for _, flab, rlab, a, b, c in combos[:12]:
    print(f"| {flab} | {rlab} | {fmt(a)} | {fmt(b)} | {fmt(c)} |")

print("\n## 4) 연도별 (최적 조합)\n")
if combos:
    _, flab, rlab, *_ = combos[0]
    kw = dict(rules)[rlab]; f = dict(filts)[flab]
    S = [s for s in sigs if f(s)]
    print(f"**{flab} + {rlab}**\n\n| 연도 | 건수 | 평균 | 승률 | PF |\n|---|---|---|---|---|")
    for y in (2023, 2024, 2025, 2026):
        st_ = stat([run(s, **kw) for s in S if s["y"] == y])
        print(f"| {y} | {st_['n'] if st_ else 0} | {st_['avg']:+.2f}% | {st_['win']:.0f}% | {st_['pf']:.2f} |" if st_ else f"| {y} | - | | | |")
