"""1번 필터(사이트 기준) 장기 백테스트: 매주 월요일 시가 매수 → 다양한 청산 규칙 비교
사용: python backtest.py 2026-01-05 2026-08-24 > 결과.md
"""
import sqlite3, io, sys, datetime as dt, statistics, bisect
import FinanceDataReader as fdr, pandas as pd
import collect

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
START = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else dt.date(2026, 1, 5)
END_ = dt.date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else dt.date(2026, 8, 24)
W, Q, B = 3, 40, 240
con = sqlite3.connect(collect.DB)
rows = con.execute("SELECT ticker,name,date,volume,frgn,close FROM daily ORDER BY ticker,date").fetchall()
S = {}
for t, n, d, v, f, c in rows:
    s = S.setdefault(t, {"n": n, "d": [], "v": [], "f": [], "a": []}); s["d"].append(d); s["v"].append(v); s["f"].append(f); s["a"].append((v or 0) * (c or 0))
avg = lambda a: sum(a) / len(a) if a else None

def hits_asof(END):
    out = []
    for t, s in S.items():
        if t[-1] != "0": continue
        k = bisect.bisect_right(s["d"], END)
        v = [x for x in s["v"][:k] if x is not None]; f = s["f"][:k]; a = s["a"][:k]
        if len(v) < W + Q + B // 2: continue
        aw, a1, a6 = avg(v[-W:]), avg(v[-(W + Q):-W]), avg(v[-(W + Q + B):-(W + Q)])
        if not (aw and a1 and a6): continue
        f5 = f[-5:]
        if any(x is None for x in f5): continue          # 외국인 데이터 없는 구간 제외
        f5s, v5 = sum(f5), sum(v[-5:])
        if a1 / a6 < .5 and aw / a1 >= 2 and f5s > 0 and f5s >= 0.02 * v5 and avg(a[-(W + Q):-W]) >= 3e8:
            out.append(dict(t=t, n=s["n"], sg=aw / a1, fp=f5s / v5 * 100, amt=avg(a[-(W + Q):-W]) / 1e8))
    return out

kospi = fdr.DataReader("KS11", (START - dt.timedelta(days=40)).isoformat(), "2026-08-28"); kospi["ma5"] = kospi["Close"].rolling(5).mean()
cache = {}
def px(t):
    if t not in cache: cache[t] = fdr.DataReader(t, START.isoformat(), "2026-08-28")
    return cache[t]
trades = []; m = START
while m <= END_:
    END = (m - dt.timedelta(days=3)).strftime("%Y%m%d"); hs = hits_asof(END)
    idx = kospi.index[kospi.index >= pd.Timestamp(m)]
    if len(idx):
        buy = idx[0]; kp = kospi[kospi.index < buy].iloc[-1]
        for h in hs:
            df = px(h["t"]); df = df[df.index >= buy]
            if len(df) == 0 or df.iloc[0]["Open"] <= 0: continue
            h.update(o=df.iloc[0]["Open"], df=df, buy=buy.strftime("%m/%d"), up=kp["Close"] > kp["ma5"], week=m); trades.append(h)
    m += dt.timedelta(weeks=1)

def sim(t, hold=10, tp=None, sl=None, trail=None):
    o, df = t["o"], t["df"]; hi = o
    for i in range(0, min(hold, len(df) - 1) + 1):
        r = df.iloc[i]
        if sl and r["Low"] <= o * (1 - sl / 100): return -sl
        if trail and hi > o and r["Low"] <= hi * (1 - trail / 100): return (hi * (1 - trail / 100) / o - 1) * 100
        if tp and r["High"] >= o * (1 + tp / 100): return tp
        hi = max(hi, r["High"])
        if i == hold: return (r["Close"] / o - 1) * 100
    return (df.iloc[-1]["Close"] / o - 1) * 100
def hold_ret(t, h):
    df = t["df"]; return (df.iloc[h]["Close"] / t["o"] - 1) * 100 if len(df) > h else None
def cell(tt, **kw):
    if len(tt) < 3: return f"표본부족({len(tt)})"
    r = [sim(t, **kw) for t in tt]; return f"{sum(r) / len(r):+.1f}% / {sum(x > 0 for x in r) / len(r) * 100:.0f}%"

print(f"# 1번 필터 백테스트 {START}~{END_} · {len(trades)}건 · 매주 월요일 시가 매수\n")
print("## 종목별\n\n| 매수일 | 종목 | 시장 | 3일/2M | 외인/거래량 | 거래대금 | 매수가 | 5일 | 10일 | 15일 | 20일 | 최고 | 최저 |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for t in trades:
    d = t["df"].iloc[:21]; cells = [f"{hold_ret(t, h):+.1f}%" if hold_ret(t, h) is not None else "—" for h in (5, 10, 15, 20)]
    print(f"| {t['buy']} | {t['n']} | {'▲' if t['up'] else '▼'} | {t['sg']:.1f}배 | {t['fp']:.1f}% | {t['amt']:.0f}억 | {t['o']:,.0f} | " + " | ".join(cells) + f" | {(d['High'].max() / t['o'] - 1) * 100:+.1f}% | {(d['Low'].min() / t['o'] - 1) * 100:+.1f}% |")
print("\n## 월별 요약 (10일 보유)\n\n| 월 | 건수 | 평균 | 승률 | 코스피 월간 |\n|---|---|---|---|---|")
for mo in sorted({t["week"].strftime("%Y-%m") for t in trades}):
    tt = [t for t in trades if t["week"].strftime("%Y-%m") == mo]; r = [sim(t, hold=10) for t in tt]
    k = kospi[kospi.index.strftime("%Y-%m") == mo]; kr = (k["Close"].iloc[-1] / k["Close"].iloc[0] - 1) * 100 if len(k) > 1 else 0
    print(f"| {mo} | {len(tt)} | {sum(r) / len(r):+.1f}% | {sum(x > 0 for x in r) / len(r) * 100:.0f}% | {kr:+.1f}% |")
H = "| 그룹 | 건수 | 1일 | 3일 | 5일 | 7일 | 10일 | 15일 | 20일 |\n|---|---|---|---|---|---|---|---|---|"
print("\n## 기간 청산 (평균 / 승률)\n\n" + H)
for g, tt in (("전체", trades), ("코스피 5일선 위 매수", [t for t in trades if t["up"]]), ("코스피 5일선 아래 매수", [t for t in trades if not t["up"]])):
    print(f"| {g} | {len(tt)} | " + " | ".join(cell(tt, hold=h) for h in (1, 3, 5, 7, 10, 15, 20)) + " |")
TP = [None, 5, 7, 10, 15, 20]; SL = [None, 5, 8, 10]
print("\n## 퍼센트 익절/손절 (최대 15일)\n\n| 익절＼손절 | " + " | ".join("없음" if s is None else f"-{s}%" for s in SL) + " |\n|---|" + "---|" * len(SL))
for tp in TP: print(f"| {'없음' if tp is None else f'+{tp}%'} | " + " | ".join(cell(trades, hold=15, tp=tp, sl=sl) for sl in SL) + " |")
print("\n## 트레일링 스탑\n\n| 보유상한 | 5% | 8% | 10% | 12% | 없음 |\n|---|---|---|---|---|---|")
for h in (10, 15, 20): print(f"| {h}일 | " + " | ".join(cell(trades, hold=h, trail=x) for x in (5, 8, 10, 12)) + f" | {cell(trades, hold=h)} |")
print("\n## 규칙 조합\n\n| 규칙 | 평균 / 승률 | 중앙값 | 최악 | 최고 |\n|---|---|---|---|---|")
for lab, kw in (("10일 보유", dict(hold=10)), ("15일 보유", dict(hold=15)), ("15일 + 트레일링 8%", dict(hold=15, trail=8)), ("15일 + 트레일링 10%", dict(hold=15, trail=10)), ("10일 + 트레일링 8%", dict(hold=10, trail=8)), ("15일 + 손절 -10%", dict(hold=15, sl=10))):
    r = [sim(t, **kw) for t in trades]; print(f"| {lab} | {sum(r) / len(r):+.2f}% / {sum(x > 0 for x in r) / len(r) * 100:.0f}% | {statistics.median(r):+.2f}% | {min(r):+.1f}% | {max(r):+.1f}% |")
up = [t for t in trades if t["up"]]
if len(up) >= 3:
    print("\n## 시장 필터 적용(코스피>5일선) + 규칙\n\n| 규칙 | 건수 | 평균 / 승률 | 중앙값 | 최악 |\n|---|---|---|---|---|")
    for lab, kw in (("15일 보유", dict(hold=15)), ("15일 + 트레일링 8%", dict(hold=15, trail=8)), ("10일 + 트레일링 8%", dict(hold=10, trail=8))):
        r = [sim(t, **kw) for t in up]; print(f"| {lab} | {len(r)} | {sum(r) / len(r):+.2f}% / {sum(x > 0 for x in r) / len(r) * 100:.0f}% | {statistics.median(r):+.2f}% | {min(r):+.1f}% |")
