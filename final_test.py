"""1번·2번 필터 다년도 최종 검증 — 손절폭 × 보유기간 최적화
python final_test.py [시작연도] [종료연도]
"""
import io, sys, pickle, itertools
from pathlib import Path
import numpy as np, pandas as pd, sqlite3
import FinanceDataReader as fdr
import collect

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
Y0 = int(sys.argv[1]) if len(sys.argv) > 1 else 2023
Y1 = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
W, Q, B = 3, 40, 240

con = sqlite3.connect(f"file:{collect.DB}?mode=ro", uri=True)
df = pd.read_sql("SELECT date,ticker,name,close,volume,frgn FROM daily WHERE ticker LIKE '%0' ORDER BY ticker,date", con)
print(f"DB {len(df):,}행 {df['date'].min()}~{df['date'].max()} · frgn 있는 행 {df['frgn'].notna().sum():,}", file=sys.stderr)

kospi = fdr.DataReader("KS11", f"{Y0-1}-06-01", "2026-08-28")
kospi["ma5"] = kospi["Close"].rolling(5).mean()
kdays = [d.strftime("%Y%m%d") for d in kospi.index]; kidx = {d: i for i, d in enumerate(kdays)}
kup = {d.strftime("%Y%m%d"): bool(r["Close"] > r["ma5"]) for d, r in kospi.iterrows()}

S1, S2 = {}, {}
for t, g in df.groupby("ticker"):
    g = g.reset_index(drop=True); v = g["volume"].astype(float); f = g["frgn"]; c = g["close"].astype(float)
    if len(g) < 320: continue
    base = ((v.shift(W).rolling(Q).mean() / v.shift(W + Q).rolling(B).mean() < .5)
            & (v.rolling(W).mean() / v.shift(W).rolling(Q).mean() >= 2)
            & (f.rolling(5).apply(lambda a: float(not np.isnan(a).any()), raw=True) == 1)
            & ((c * v).shift(W).rolling(Q).mean() / 1e8 >= 3))
    fwp = f.rolling(5).sum() / v.rolling(5).sum() * 100
    ret3 = (c / c.shift(3) - 1) * 100
    inrange = (g["date"] >= f"{Y0}0101") & (g["date"] <= f"{Y1}1231")
    m1 = base & (fwp >= 2) & inrange
    m2 = base & (fwp >= 5) & (ret3 > 0) & (ret3 <= 10) & inrange
    if m1.any(): S1[t] = set(g.loc[m1, "date"])
    if m2.any(): S2[t] = set(g.loc[m2, "date"])
print(f"1번 신호종목 {len(S1)} · 2번 {len(S2)}", file=sys.stderr)

CF = BASE / "data" / "ohlc_final.pkl"
cache = pickle.load(open(CF, "rb")) if CF.exists() else {}
def px(t):
    if t not in cache:
        try: cache[t] = fdr.DataReader(t, f"{Y0}-01-01", "2026-08-28")
        except Exception: cache[t] = pd.DataFrame()
    return cache[t]

def entries(SIG, consec):
    T = []
    need = sorted(SIG)
    for n, t in enumerate(need):
        ds = SIG[t]; last = -99
        d_all = px(t)
        if n % 100 == 0: pickle.dump(cache, open(CF, "wb")); print(f"  가격 {n}/{len(need)}", file=sys.stderr)
        if len(d_all) == 0: continue
        for d in sorted(ds):
            i = kidx.get(d)
            if i is None or i + 1 >= len(kdays): continue
            prev = i >= 1 and kdays[i - 1] in ds
            ok = (prev and not (i >= 2 and kdays[i - 2] in ds)) if consec == 2 else (not prev)
            if ok and i - last >= 15:
                dd = d_all[d_all.index >= pd.Timestamp(kdays[i + 1])]
                if len(dd) == 0 or dd.iloc[0]["Open"] <= 0: continue
                last = i
                T.append(dict(o=float(dd.iloc[0]["Open"]), df=dd, up=kup.get(d, False), d=d, y=int(d[:4]), t=t))
    pickle.dump(cache, open(CF, "wb"))
    return T

T1 = entries(S1, 2); T2 = entries(S2, 1)
T1u = [t for t in T1 if t["up"]]; T2u = [t for t in T2 if t["up"]]
print(f"1번 진입 {len(T1)}건(5일선 위 {len(T1u)}) · 2번 {len(T2)}건({len(T2u)})", file=sys.stderr)

def run(tr, hold=15, sl=None, trail=None):
    o, d = tr["o"], tr["df"]; hi = o
    if len(d) <= hold: return None
    for i in range(hold + 1):
        lo, h = d["Low"].iloc[i], d["High"].iloc[i]
        if sl and lo <= o * (1 - sl / 100): return -sl
        if trail and hi > o and lo <= hi * (1 - trail / 100): return (hi * (1 - trail / 100) / o - 1) * 100
        hi = max(hi, h)
    return (d["Close"].iloc[hold] / o - 1) * 100

def stat(rs):
    r = [x for x in rs if x is not None]
    if len(r) < 10: return None
    w = [v for v in r if v > 0]; l = [v for v in r if v <= 0]
    return dict(n=len(r), avg=np.mean(r), win=len(w) / len(r) * 100, pf=(sum(w) / abs(sum(l))) if l else 99,
                med=np.median(r), worst=min(r))
def f(s): return f"{s['avg']:+.2f}% / {s['win']:.0f}% / {s['pf']:.2f}" if s else "-"

print(f"# 1번·2번 필터 다년도 최종 검증 ({Y0}~{Y1})\n")
print(f"1번 필터(2일 연속) {len(T1)}건 · 코스피 5일선 위 {len(T1u)}건\n2번 필터(당일) {len(T2)}건 · 5일선 위 {len(T2u)}건\n")
print("표기: 평균 / 승률 / PF\n")

for nm, TT in (("1번 필터", T1u), ("2번 필터", T2u)):
    print(f"\n## {nm} — 손절폭 × 보유기간 (코스피 5일선 위 매수만)\n")
    print("| 손절＼보유 | 5일 | 10일 | 15일 | 20일 | 30일 |\n|---|---|---|---|---|---|")
    for sl in (None, 5, 7, 8, 10, 12, 15, 20):
        cells = [f(stat([run(t, hold=h, sl=sl) for t in TT])) for h in (5, 10, 15, 20, 30)]
        print(f"| {'없음' if sl is None else f'-{sl}%'} | " + " | ".join(cells) + " |")
    print(f"\n### 연도별 (15일 보유 · 손절 -10%)\n\n| 연도 | 건수 | 평균 | 승률 | PF | 최악 |\n|---|---|---|---|---|---|")
    for y in range(Y0, Y1 + 1):
        s = stat([run(t, hold=15, sl=10) for t in TT if t["y"] == y])
        print(f"| {y} | {s['n']} | {s['avg']:+.2f}% | {s['win']:.0f}% | {s['pf']:.2f} | {s['worst']:+.0f}% |" if s else f"| {y} | 표본부족 | | | | |")
    print(f"\n### 시장 필터 효과 (15일 · 손절 -10%)\n")
    ALL = T1 if nm == "1번 필터" else T2
    up = [t for t in ALL if t["up"]]; dn = [t for t in ALL if not t["up"]]
    print(f"| 구분 | 건수 | 성과 |\n|---|---|---|")
    print(f"| 코스피 5일선 위 | {len(up)} | {f(stat([run(t, hold=15, sl=10) for t in up]))} |")
    print(f"| 코스피 5일선 아래 | {len(dn)} | {f(stat([run(t, hold=15, sl=10) for t in dn]))} |")
    print(f"\n### 최적 조합 상위 5 (연도별 모두 플러스인 것만)\n")
    cands = []
    for sl in (None, 5, 7, 8, 10, 12, 15, 20):
        for h in (5, 10, 15, 20, 30):
            per_y = [stat([run(t, hold=h, sl=sl) for t in TT if t["y"] == y]) for y in range(Y0, Y1 + 1)]
            per_y = [x for x in per_y if x]
            if len(per_y) < 2 or any(x["avg"] <= 0 for x in per_y): continue
            a = stat([run(t, hold=h, sl=sl) for t in TT])
            if a: cands.append((a["pf"], sl, h, a, min(x["win"] for x in per_y)))
    cands.sort(reverse=True, key=lambda x: x[0])
    print("| 손절 | 보유 | 전체 | 최저연도 승률 |\n|---|---|---|---|")
    for pf, sl, h, a, mw in cands[:5]:
        print(f"| {'없음' if sl is None else f'-{sl}%'} | {h}일 | {f(a)} · 최악 {a['worst']:+.0f}% | {mw:.0f}% |")
    if not cands: print("| (연도별 전부 플러스인 조합 없음) | | | |")
