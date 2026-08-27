"""조건 탐색: 1번 필터 계열 변형 중 승률 65%+ 조합 찾기 (1~4월 탐색 → 5~8월 검증)
python search.py > 결과.md
"""
import sqlite3, io, sys, pickle, itertools, datetime as dt, statistics
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr
import collect

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
con = sqlite3.connect(collect.DB)
df = pd.read_sql("SELECT date,ticker,name,close,volume,frgn FROM daily WHERE ticker LIKE '%0' ORDER BY ticker,date", con)
df["amt"] = df["close"] * df["volume"]
kospi = fdr.DataReader("KS11", "2025-11-01", "2026-08-28")
kospi["ma5"] = kospi["Close"].rolling(5).mean(); kospi["ma20"] = kospi["Close"].rolling(20).mean()
kdays = [d.strftime("%Y%m%d") for d in kospi.index]
kup5 = {d.strftime("%Y%m%d"): r["Close"] > r["ma5"] for d, r in kospi.iterrows()}
kup20 = {d.strftime("%Y%m%d"): r["Close"] > r["ma20"] for d, r in kospi.iterrows()}
START, SPLIT, END = "20260105", "20260501", "20260826"

# ---- 종목별 피처 ----
feat = []
for t, g in df.groupby("ticker"):
    g = g.reset_index(drop=True)
    v = g["volume"].astype(float); f = g["frgn"]; c = g["close"].astype(float)
    if len(g) < 300: continue
    base = v.shift(43).rolling(240).mean()          # 기준창(잠잠창 이전 240일) — W=3 기준 위치
    quiet = v.shift(3).rolling(40).mean()           # 잠잠창 40일 (W=3 기준)
    out = pd.DataFrame({"date": g["date"], "t": t, "n": g["name"], "close": c})
    for W in (2, 3, 5):
        out[f"surge{W}"] = v.rolling(W).mean() / v.shift(W).rolling(40).mean()
    out["quiet"] = quiet / base
    out["f5"] = f.rolling(5).sum() / v.rolling(5).sum()
    out["fok"] = f.rolling(5).apply(lambda a: float(not np.isnan(a).any()), raw=True)
    out["amt40"] = (c * v).shift(3).rolling(40).mean() / 1e8
    out["ret1"] = c.pct_change() * 100
    out["ret3"] = c.pct_change(3) * 100
    out["hi20"] = c / c.rolling(20).max()
    feat.append(out)
F = pd.concat(feat); F = F[(F["date"] >= START) & (F["date"] <= END) & (F["fok"] == 1)].copy()
print(f"피처 행: {len(F):,}  종목 {F['t'].nunique()}", file=sys.stderr)

# ---- 가격 캐시 (OHLC) ----
cache_f = BASE / "data" / "ohlc_cache.pkl"
cache = pickle.load(open(cache_f, "rb")) if cache_f.exists() else {}
def px(t):
    if t not in cache:
        try: cache[t] = fdr.DataReader(t, "2026-01-01", "2026-08-28")
        except Exception: cache[t] = pd.DataFrame()
    return cache[t]

# ---- 기본(가장 느슨한) 신호로 후보 종목 한정 ----
loose = F[(F["quiet"] < 0.5) & (F["surge2"] >= 2) & (F["f5"] > 0.02) & (F["amt40"] >= 3)]
loose = pd.concat([loose, F[(F["quiet"] < 0.5) & (F["surge3"] >= 2) & (F["f5"] > 0.02) & (F["amt40"] >= 3)], F[(F["quiet"] < 0.5) & (F["surge5"] >= 2) & (F["f5"] > 0.02) & (F["amt40"] >= 3)]]).drop_duplicates(["date", "t"])
need = sorted(loose["t"].unique()); print(f"가격 필요 종목 {len(need)}", file=sys.stderr)
for i, t in enumerate(need):
    px(t)
    if i % 100 == 0: pickle.dump(cache, open(cache_f, "wb"))
pickle.dump(cache, open(cache_f, "wb"))

def outcome(t, sig_date, hold, trail):
    d = px(t); nxt = [x for x in kdays if x > sig_date]
    if d.empty or not nxt: return None
    d = d[d.index >= pd.Timestamp(nxt[0])]
    if len(d) == 0 or d.iloc[0]["Open"] <= 0: return None
    o = d.iloc[0]["Open"]; hi = o
    for i in range(0, min(hold, len(d) - 1) + 1):
        r = d.iloc[i]
        if trail and hi > o and r["Low"] <= hi * (1 - trail / 100): return (hi * (1 - trail / 100) / o - 1) * 100
        hi = max(hi, r["High"])
        if i == hold: return (r["Close"] / o - 1) * 100
    return (d.iloc[-1]["Close"] / o - 1) * 100

# ---- 조합 탐색 ----
Fs = F.set_index(["t", "date"]).sort_index()
grid = dict(W=[2, 3, 5], quiet=[0.5, 0.4, 0.3], surge=[2, 3, 4], f5=[0.02, 0.05, 0.10], amt=[3, 10, 30], conf=[1, 2, 3], mkt=["none", "ma5", "ma20"],
            px=["any", "up_day", "ret3_0_10", "near_hi"])
results = []
combos = list(itertools.product(*grid.values()))
print(f"조합 {len(combos)}", file=sys.stderr)
date_idx = {d: i for i, d in enumerate(kdays)}
for ci, vals in enumerate(combos):
    W, q, sg, f5, amt, conf, mkt, pxf = vals
    m = (F["quiet"] < q) & (F[f"surge{W}"] >= sg) & (F["f5"] >= f5) & (F["amt40"] >= amt)
    if pxf == "up_day": m &= F["ret1"] > 0
    elif pxf == "ret3_0_10": m &= (F["ret3"] > 0) & (F["ret3"] <= 10)
    elif pxf == "near_hi": m &= F["hi20"] >= 0.97
    S = F[m][["t", "date"]]
    if len(S) == 0: continue
    if mkt == "ma5": S = S[S["date"].map(kup5).fillna(False)]
    elif mkt == "ma20": S = S[S["date"].map(kup20).fillna(False)]
    # 연속 확인 + 15일 내 재진입 제외
    trades = []
    for t, g in S.groupby("t"):
        ds = sorted(g["date"]); idx = [date_idx.get(d, -99) for d in ds]; last = -99
        for j, d in enumerate(ds):
            run = 1; qq = j
            while qq > 0 and idx[qq] - idx[qq - 1] == 1: run += 1; qq -= 1
            if run >= conf and idx[j] - last >= 15 and (run == conf):
                last = idx[j]; trades.append((t, d))
    if len(trades) < 25: continue
    rows = []
    for t, d in trades:
        r10 = outcome(t, d, 10, 10); r15 = outcome(t, d, 15, 10); r15n = outcome(t, d, 15, None)
        if r10 is None: continue
        rows.append((d, r10, r15, r15n))
    if len(rows) < 25: continue
    a = [r for r in rows if r[0] < SPLIT]; b = [r for r in rows if r[0] >= SPLIT]
    def st(rs, k):
        x = [r[k] for r in rs if r[k] is not None]; return (len(x), sum(x) / len(x), sum(v > 0 for v in x) / len(x) * 100) if x else (0, 0, 0)
    results.append(dict(combo=vals, n=len(rows), all10=st(rows, 1), all15=st(rows, 2), all15n=st(rows, 3), a15=st(a, 2), b15=st(b, 2), a10=st(a, 1), b10=st(b, 1)))
    if ci % 200 == 0: print(f"{ci}/{len(combos)} 결과 {len(results)}", file=sys.stderr)

def fmt(s): return f"{s[1]:+.1f}%/{s[2]:.0f}% ({s[0]})"
print("# 조건 탐색 결과 (매일 조회 · 재진입 제외 · 트레일링 10%)\n")
print("표기: 평균/승률 (건수) · 탐색기간 1~4월, 검증기간 5~8월\n")
def table(title, rs, key):
    print(f"## {title}\n\n| W | 잠잠< | 급등≥ | 외인≥ | 거래대금≥ | 확인일 | 시장 | 주가 | 건수 | 전체 10일 | 전체 15일 | 15일(트레일 없음) | 1~4월 15일 | 5~8월 15일 |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rs[:20]:
        W, q, sg, f5, amt, conf, mkt, pxf = r["combo"]
        print(f"| {W} | {q:.0%} | {sg}배 | {f5:.0%} | {amt}억 | {conf} | {mkt} | {pxf} | {r['n']} | {fmt(r['all10'])} | {fmt(r['all15'])} | {fmt(r['all15n'])} | {fmt(r['a15'])} | {fmt(r['b15'])} |")
    print()
robust = [r for r in results if r["a15"][0] >= 12 and r["b15"][0] >= 12 and r["a15"][2] >= 60 and r["b15"][2] >= 60]
robust.sort(key=lambda r: -min(r["a15"][2], r["b15"][2]))
table("두 구간 모두 승률 60%+ (15일+트레일10%), 낮은 쪽 승률순", robust, None)
robust10 = [r for r in results if r["a10"][0] >= 12 and r["b10"][0] >= 12 and r["a10"][2] >= 60 and r["b10"][2] >= 60]
robust10.sort(key=lambda r: -min(r["a10"][2], r["b10"][2]))
table("두 구간 모두 승률 60%+ (10일+트레일10%)", robust10, None)
top = sorted([r for r in results if r["n"] >= 40], key=lambda r: -r["all15"][2])
table("전체 기간 승률 상위 (건수 40+, 15일+트레일10%) — 과최적화 주의", top, None)
print(f"\n총 평가 조합 {len(results)} / 탐색 {len(combos)}")
