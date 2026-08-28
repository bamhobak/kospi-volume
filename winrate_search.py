"""승률 55%+ 조합 탐색 — 진입조건 × 청산규칙 전수 그리드 (2023~2026)
python winrate_search.py
"""
import io, sys, pickle, itertools, sqlite3
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr
import collect

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
W, Q, B = 3, 40, 240
NB = 31   # 미래 경로 저장 봉수

con = sqlite3.connect(f"file:{collect.DB}?mode=ro", uri=True)
df = pd.read_sql("SELECT date,ticker,name,close,volume,frgn,organ,indiv FROM daily WHERE ticker LIKE '%0' ORDER BY ticker,date", con)
kospi = fdr.DataReader("KS11", "2022-06-01", "2026-08-28")
kospi["ma5"] = kospi["Close"].rolling(5).mean(); kospi["ma20"] = kospi["Close"].rolling(20).mean()
kdays = [d.strftime("%Y%m%d") for d in kospi.index]; kidx = {d: i for i, d in enumerate(kdays)}
kup5 = {d.strftime("%Y%m%d"): bool(r["Close"] > r["ma5"]) for d, r in kospi.iterrows()}
kup20 = {d.strftime("%Y%m%d"): bool(r["Close"] > r["ma20"]) for d, r in kospi.iterrows()}

CF = BASE / "data" / "ohlc_final.pkl"
cache = pickle.load(open(CF, "rb")) if CF.exists() else {}
def px(t):
    if t not in cache:
        try: cache[t] = fdr.DataReader(t, "2023-01-01", "2026-08-28")
        except Exception: cache[t] = pd.DataFrame()
    return cache[t]

SIG = []
for n, (t, g) in enumerate(df.groupby("ticker")):
    g = g.reset_index(drop=True)
    v = g["volume"].astype(float); f = g["frgn"]; c = g["close"].astype(float); o_ = g["organ"]
    if len(g) < 320: continue
    quiet = v.shift(W).rolling(Q).mean() / v.shift(W + Q).rolling(B).mean()
    surge = v.rolling(W).mean() / v.shift(W).rolling(Q).mean()
    v5 = v.rolling(5).sum()
    fwp = f.rolling(5).sum() / v5 * 100
    owp = o_.rolling(5).sum() / v5 * 100
    fok = f.rolling(5).apply(lambda a: float(not np.isnan(a).any()), raw=True)
    amt = (c * v).shift(W).rolling(Q).mean() / 1e8
    ret1 = (c / c.shift(1) - 1) * 100; ret3 = (c / c.shift(3) - 1) * 100; ret10 = (c / c.shift(10) - 1) * 100
    ma20 = c.rolling(20).mean(); ma60 = c.rolling(60).mean()
    base = (quiet < .6) & (surge >= 2) & (fok == 1) & (amt >= 1) & (g["date"] >= "20230101")
    idx = np.where(base.values)[0]
    if len(idx) == 0: continue
    dts = g["date"].values
    prev_ok = {}
    dset = set(dts[idx])
    d_all = px(t)
    if len(d_all) == 0: continue
    last = -99
    for j in idx:
        d = dts[j]; ki = kidx.get(d)
        if ki is None or ki + 1 >= len(kdays): continue
        if ki - last < 15: continue
        # 연속 충족 일수
        streak = 1
        for back in range(1, 6):
            if ki - back < 0: break
            if kdays[ki - back] in dset: streak += 1
            else: break
        dd = d_all[d_all.index >= pd.Timestamp(kdays[ki + 1])]
        if len(dd) < 21 or dd.iloc[0]["Open"] <= 0: continue
        last = ki
        o0 = float(dd.iloc[0]["Open"])
        H = (dd["High"].values[:NB] / o0 - 1) * 100
        L = (dd["Low"].values[:NB] / o0 - 1) * 100
        C = (dd["Close"].values[:NB] / o0 - 1) * 100
        SIG.append(dict(t=t, d=d, y=int(d[:4]), H=H, L=L, C=C, name=g["name"].iloc[j],
                        quiet=float(quiet.iloc[j]), surge=float(surge.iloc[j]), fwp=float(fwp.iloc[j]),
                        owp=float(owp.iloc[j]) if not np.isnan(owp.iloc[j]) else 0.0, amt=float(amt.iloc[j]),
                        streak=streak, ret1=float(ret1.iloc[j]), ret3=float(ret3.iloc[j]), ret10=float(ret10.iloc[j]),
                        above20=bool(c.iloc[j] > ma20.iloc[j]) if not np.isnan(ma20.iloc[j]) else False,
                        above60=bool(c.iloc[j] > ma60.iloc[j]) if not np.isnan(ma60.iloc[j]) else False,
                        k5=kup5.get(d, False), k20=kup20.get(d, False)))
    if n % 200 == 0: pickle.dump(cache, open(CF, "wb")); print(f"  {n}종목 · 신호 {len(SIG)}", file=sys.stderr)
pickle.dump(cache, open(CF, "wb"))
print(f"기본 신호 {len(SIG)}건", file=sys.stderr)

def evaluate(s, hold, sl, tp):
    H, L, C = s["H"], s["L"], s["C"]
    n = min(hold, len(C) - 1)
    for i in range(n + 1):
        if sl is not None and L[i] <= -sl: return -sl
        if tp is not None and H[i] >= tp: return tp
        if i == n: return C[i]
    return C[n]

def summarize(rows):
    if len(rows) < 20: return None
    r = np.array(rows); w = r[r > 0]; l = r[r <= 0]
    return dict(n=len(r), avg=r.mean(), win=len(w) / len(r) * 100,
                pf=(w.sum() / abs(l.sum())) if len(l) else 99, med=np.median(r))

FILTERS = {
    "surge": [(2, "2배↑"), (3, "3배↑"), (5, "5배↑")],
    "fwp": [(0, "무관"), (2, "2%↑"), (5, "5%↑"), (10, "10%↑"), (20, "20%↑")],
    "amt": [(3, "3억↑"), (10, "10억↑"), (50, "50억↑")],
    "streak": [(1, "1일↑"), (2, "2일연속↑"), (3, "3일연속↑")],
    "quiet": [(0.6, "무관"), (0.5, "2M<1Y의50%"), (0.3, "30%(매우잠잠)")],
    "organ": [(-99, "무관"), (0, "기관도 순매수")],
    "mkt": [("none", "무관"), ("k5", "코스피>5일선"), ("k20", "코스피>20일선"), ("both", "5일선+20일선")],
    "px": [("none", "무관"), ("up20", "20일선 위"), ("ret3lim", "3일 0~10%"), ("ret3neg", "3일 하락"), ("cool", "10일 0~20%")],
}
def passes(s, sg, fw, am, st, qt, og, mk, pxc):
    if s["surge"] < sg or s["fwp"] < fw or s["amt"] < am or s["streak"] < st: return False
    if s["quiet"] >= qt: return False
    if og > -99 and s["owp"] <= og: return False
    if mk == "k5" and not s["k5"]: return False
    if mk == "k20" and not s["k20"]: return False
    if mk == "both" and not (s["k5"] and s["k20"]): return False
    if pxc == "up20" and not s["above20"]: return False
    if pxc == "ret3lim" and not (0 < s["ret3"] <= 10): return False
    if pxc == "ret3neg" and not (s["ret3"] <= 0): return False
    if pxc == "cool" and not (0 <= s["ret10"] <= 20): return False
    return True

EXITS = [(h, sl, tp) for h in (3, 5, 7, 10, 15, 20) for sl in (None, 5, 7, 10, 15) for tp in (None, 3, 5, 7, 10, 15)]
results = []
KEYS = ("surge", "fwp", "amt", "streak", "quiet", "organ", "mkt", "px")
combos = list(itertools.product(*[[x[0] for x in FILTERS[k]] for k in KEYS]))
print(f"진입 조합 {len(combos)} × 청산 {len(EXITS)}", file=sys.stderr)
for ci, cfg0 in enumerate(combos):
    S = [s for s in SIG if passes(s, *cfg0)]
    if len(S) < 40: continue
    years = sorted({s["y"] for s in S})
    for (h, sl, tp) in EXITS:
        rows = [evaluate(s, h, sl, tp) for s in S]
        a = summarize(rows)
        if not a or a["win"] < 55 or a["avg"] <= 0.3: continue
        per = []
        okY = True
        for y in years:
            ry = [evaluate(s, h, sl, tp) for s in S if s["y"] == y]
            if len(ry) < 8: continue
            sy = summarize(ry)
            if not sy: continue
            per.append((y, sy))
            if sy["avg"] <= 0: okY = False
        if len(per) < 3: continue
        results.append(dict(cfg=tuple(cfg0) + (h, sl, tp), a=a, per=per, allpos=okY,
                            minwin=min(p[1]["win"] for p in per)))
    if ci % 50 == 0: print(f"  {ci}/{len(combos)} 후보 {len(results)}", file=sys.stderr)

lab = {k: dict(FILTERS[k]) for k in FILTERS}
def name(cfg):
    sg, fw, am, st, qt, og, mk, pxc, h, sl, tp = cfg
    return (f"급등{lab['surge'][sg]} · 외인{lab['fwp'][fw]} · 대금{lab['amt'][am]} · {lab['streak'][st]} · 잠잠{lab['quiet'][qt]} · "
            f"{lab['organ'][og]} · {lab['mkt'][mk]} · {lab['px'][pxc]} → {h}일"
            + (f" · 손절 -{sl}%" if sl else " · 손절없음") + (f" · 익절 +{tp}%" if tp else " · 익절없음"))

print("# 승률 55%+ 조합 탐색 결과 (2023~2026)\n")
print(f"기본 신호 {len(SIG)}건 · 조건을 만족하는 조합 {len(results)}개\n")
print("표기: 평균 / 승률 / PF (건수)\n")

strict = [r for r in results if r["allpos"]]
strict.sort(key=lambda r: -(r["a"]["avg"]))
print(f"## A. 연도별 전부 플러스 + 승률 55%+ ({len(strict)}개) — 평균수익 상위 15\n")
print("| 조건 | 전체 | 연도별 최저 승률 | 연도별 평균 |\n|---|---|---|---|")
for r in strict[:15]:
    a = r["a"]; ys = " / ".join(f"{y}:{s['avg']:+.1f}%" for y, s in r["per"])
    print(f"| {name(r['cfg'])} | {a['avg']:+.2f}% / {a['win']:.0f}% / {a['pf']:.2f} ({a['n']}) | {r['minwin']:.0f}% | {ys} |")

print(f"\n## B. 승률 최상위 15 (연도 조건 무관)\n")
results.sort(key=lambda r: -(r["a"]["win"]))
print("| 조건 | 전체 | 연도별 평균 |\n|---|---|---|")
for r in results[:15]:
    a = r["a"]; ys = " / ".join(f"{y}:{s['avg']:+.1f}%" for y, s in r["per"])
    print(f"| {name(r['cfg'])} | {a['avg']:+.2f}% / {a['win']:.0f}% / {a['pf']:.2f} ({a['n']}) | {ys} |")

print(f"\n## C. PF 상위 15 (승률 55%+)\n")
results.sort(key=lambda r: -(r["a"]["pf"]))
print("| 조건 | 전체 | 연도별 평균 |\n|---|---|---|")
for r in results[:15]:
    a = r["a"]; ys = " / ".join(f"{y}:{s['avg']:+.1f}%" for y, s in r["per"])
    print(f"| {name(r['cfg'])} | {a['avg']:+.2f}% / {a['win']:.0f}% / {a['pf']:.2f} ({a['n']}) | {ys} |")
