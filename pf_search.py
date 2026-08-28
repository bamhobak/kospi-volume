"""승률 50%+ 중 PF 최상위 조합 탐색 — 슬리피지 반영, 다각도
python pf_search.py
"""
import io, sys, pickle, itertools, sqlite3
from pathlib import Path
import numpy as np, pandas as pd, FinanceDataReader as fdr
import collect

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
W, Q, B = 3, 40, 240; NB = 31
SIGF = BASE / "data" / "sig_cache.pkl"

if SIGF.exists():
    SIG = pickle.load(open(SIGF, "rb"))
else:
    con = sqlite3.connect(f"file:{collect.DB}?mode=ro", uri=True)
    df = pd.read_sql("SELECT date,ticker,name,close,volume,frgn,organ,indiv FROM daily WHERE ticker LIKE '%0' ORDER BY ticker,date", con)
    kospi = fdr.DataReader("KS11", "2022-06-01", "2026-08-28")
    kospi["ma5"] = kospi["Close"].rolling(5).mean(); kospi["ma20"] = kospi["Close"].rolling(20).mean()
    kospi["ma60"] = kospi["Close"].rolling(60).mean()
    kdays = [d.strftime("%Y%m%d") for d in kospi.index]; kidx = {d: i for i, d in enumerate(kdays)}
    K = {d.strftime("%Y%m%d"): (bool(r["Close"] > r["ma5"]), bool(r["Close"] > r["ma20"]), bool(r["Close"] > r["ma60"]))
         for d, r in kospi.iterrows()}
    cache = pickle.load(open(BASE / "data" / "ohlc_final.pkl", "rb"))
    SIG = []
    for t, g in df.groupby("ticker"):
        g = g.reset_index(drop=True)
        v = g["volume"].astype(float); f = g["frgn"]; c = g["close"].astype(float); og = g["organ"]
        if len(g) < 320: continue
        quiet = v.shift(W).rolling(Q).mean() / v.shift(W + Q).rolling(B).mean()
        surge = v.rolling(W).mean() / v.shift(W).rolling(Q).mean()
        v5 = v.rolling(5).sum(); fwp = f.rolling(5).sum() / v5 * 100; owp = og.rolling(5).sum() / v5 * 100
        fok = f.rolling(5).apply(lambda a: float(not np.isnan(a).any()), raw=True)
        amt = (c * v).shift(W).rolling(Q).mean() / 1e8
        ret1 = (c / c.shift(1) - 1) * 100; ret3 = (c / c.shift(3) - 1) * 100
        ret10 = (c / c.shift(10) - 1) * 100; ret60 = (c / c.shift(60) - 1) * 100
        ma20 = c.rolling(20).mean(); ma60c = c.rolling(60).mean(); hi60 = c.rolling(60).max()
        base = (quiet < .7) & (surge >= 2) & (fok == 1) & (amt >= 1) & (g["date"] >= "20230101")
        idx = np.where(base.values)[0]
        if len(idx) == 0: continue
        dts = g["date"].values; d_all = cache.get(t)
        if d_all is None or len(d_all) == 0: continue
        last = -99
        for j in idx:
            d = dts[j]; ki = kidx.get(d)
            if ki is None or ki + 1 >= len(kdays) or ki - last < 15: continue
            dd = d_all[d_all.index >= pd.Timestamp(kdays[ki + 1])]
            if len(dd) < 21 or dd.iloc[0]["Open"] <= 0: continue
            last = ki; o0 = float(dd.iloc[0]["Open"]); k5, k20, k60 = K.get(d, (False, False, False))
            SIG.append(dict(t=t, d=d, y=int(d[:4]),
                H=(dd["High"].values[:NB] / o0 - 1) * 100, L=(dd["Low"].values[:NB] / o0 - 1) * 100,
                C=(dd["Close"].values[:NB] / o0 - 1) * 100,
                quiet=float(quiet.iloc[j]), surge=float(surge.iloc[j]), fwp=float(fwp.iloc[j]),
                owp=float(owp.iloc[j]) if not np.isnan(owp.iloc[j]) else 0.0, amt=float(amt.iloc[j]),
                ret1=float(ret1.iloc[j]), ret3=float(ret3.iloc[j]), ret10=float(ret10.iloc[j]),
                ret60=float(ret60.iloc[j]) if not np.isnan(ret60.iloc[j]) else 0.0,
                a20=bool(c.iloc[j] > ma20.iloc[j]) if not np.isnan(ma20.iloc[j]) else False,
                a60=bool(c.iloc[j] > ma60c.iloc[j]) if not np.isnan(ma60c.iloc[j]) else False,
                nearhi=float(c.iloc[j] / hi60.iloc[j]) if not np.isnan(hi60.iloc[j]) and hi60.iloc[j] else 0.0,
                k5=k5, k20=k20, k60=k60))
    pickle.dump(SIG, open(SIGF, "wb"))
print(f"기본 신호 {len(SIG)}건", file=sys.stderr)

def cost(a):
    slip = 0.20 if a >= 100 else 0.30 if a >= 50 else 0.50 if a >= 20 else 0.70 if a >= 10 else 1.00
    return 0.18 + slip
for s in SIG: s["cost"] = cost(s["amt"])

def ev(s, h, sl, tp):
    H, L, C = s["H"], s["L"], s["C"]; n = min(h, len(C) - 1)
    for i in range(n + 1):
        if sl and L[i] <= -sl: return -sl - s["cost"]
        if tp and H[i] >= tp: return tp - s["cost"]
        if i == n: return C[i] - s["cost"]

F = {
 "surge": [2, 2.5, 3, 4],
 "fwp":   [0, 2, 5, 10],
 "amt":   [3, 10, 30, 50, 100],
 "quiet": [0.7, 0.5, 0.4, 0.3],
 "organ": [-99, 0],
 "mkt":   ["none", "k5", "k20", "both", "k60"],
 "px":    ["none", "r3neg", "r3pos", "r10cool", "r10neg", "a20", "nearhi"],
}
MK = {"none": "시장무관", "k5": "코스피>5일", "k20": "코스피>20일", "both": "5+20일", "k60": "코스피>60일"}
PX = {"none": "주가무관", "r3neg": "3일 하락", "r3pos": "3일 상승", "r10cool": "10일 0~20%",
      "r10neg": "10일 하락", "a20": "20일선 위", "nearhi": "60일 고점 3% 이내"}
def ok(s, sg, fw, am, qt, og, mk, pxc):
    if s["surge"] < sg or s["fwp"] < fw or s["amt"] < am or s["quiet"] >= qt: return False
    if og > -99 and s["owp"] <= og: return False
    if mk == "k5" and not s["k5"]: return False
    if mk == "k20" and not s["k20"]: return False
    if mk == "k60" and not s["k60"]: return False
    if mk == "both" and not (s["k5"] and s["k20"]): return False
    if pxc == "r3neg" and s["ret3"] > 0: return False
    if pxc == "r3pos" and s["ret3"] <= 0: return False
    if pxc == "r10cool" and not (0 <= s["ret10"] <= 20): return False
    if pxc == "r10neg" and s["ret10"] > 0: return False
    if pxc == "a20" and not s["a20"]: return False
    if pxc == "nearhi" and s["nearhi"] < 0.97: return False
    return True

EX = [(h, sl, tp) for h in (3, 5, 7, 10, 15, 20) for sl in (None, 7, 10, 15, 20) for tp in (None, 10, 15, 20)]
res = []
combos = list(itertools.product(*F.values()))
print(f"진입 {len(combos)} × 청산 {len(EX)}", file=sys.stderr)
for ci, cfg in enumerate(combos):
    S = [s for s in SIG if ok(s, *cfg)]
    if len(S) < 40: continue
    ys = sorted({s["y"] for s in S})
    for h, sl, tp in EX:
        r = np.array([ev(s, h, sl, tp) for s in S])
        w = r[r > 0]; l = r[r <= 0]
        win = len(w) / len(r) * 100
        if win < 50 or r.mean() <= 0.5: continue
        pf = (w.sum() / abs(l.sum())) if len(l) else 99
        per = []; allpos = True
        for y in ys:
            ry = np.array([ev(s, h, sl, tp) for s in S if s["y"] == y])
            if len(ry) < 10: continue
            per.append((y, ry.mean(), (ry > 0).mean() * 100))
            if ry.mean() <= 0: allpos = False
        if len(per) < 3: continue
        res.append(dict(cfg=cfg + (h, sl, tp), n=len(r), avg=r.mean(), win=win, pf=pf, per=per, allpos=allpos,
                        minw=min(p[2] for p in per)))
    if ci % 400 == 0: print(f"  {ci}/{len(combos)} 후보 {len(res)}", file=sys.stderr)

def nm(c):
    sg, fw, am, qt, og, mk, pxc, h, sl, tp = c
    return (f"급등{sg}배↑ · 외인{fw}%↑ · 대금{am}억↑ · 잠잠<{qt} · {'기관+' if og > -99 else '기관무관'} · {MK[mk]} · {PX[pxc]}"
            f" → {h}일" + (f" · 손절-{sl}%" if sl else " · 손절X") + (f" · 익절+{tp}%" if tp else " · 익절X"))

print(f"# 승률 50%+ 중 PF 최상위 (슬리피지 반영, 2023~2026)\n")
print(f"평가 조합 {len(res)}개 · 기본 신호 {len(SIG)}건\n")
print("표기: 순수익 / 승률 / PF (건수)\n")

A = [r for r in res if r["allpos"]]
A.sort(key=lambda r: -r["pf"])
print(f"## A. PF 최상위 — 연도별 전부 플러스 ({len(A)}개 중 20)\n")
print("| 조건 | 순수익/승률/PF | 연도별 순수익 |\n|---|---|---|")
for r in A[:20]:
    print(f"| {nm(r['cfg'])} | {r['avg']:+.2f}% / {r['win']:.0f}% / **{r['pf']:.2f}** ({r['n']}) | "
          + " / ".join(f"{y}:{v:+.1f}%" for y, v, _ in r["per"]) + " |")

A2 = [r for r in A if r["n"] >= 80]
A2.sort(key=lambda r: -r["pf"])
print(f"\n## B. PF 최상위 — 표본 80건 이상 ({len(A2)}개 중 12)\n")
print("| 조건 | 순수익/승률/PF | 연도별 |\n|---|---|---|")
for r in A2[:12]:
    print(f"| {nm(r['cfg'])} | {r['avg']:+.2f}% / {r['win']:.0f}% / **{r['pf']:.2f}** ({r['n']}) | "
          + " / ".join(f"{y}:{v:+.1f}%" for y, v, _ in r["per"]) + " |")

A3 = [r for r in A if len(r["per"]) >= 4]
A3.sort(key=lambda r: -r["pf"])
print(f"\n## C. PF 최상위 — 4개 연도 모두 데이터 있고 전부 플러스 ({len(A3)}개 중 12)\n")
print("| 조건 | 순수익/승률/PF | 연도별 |\n|---|---|---|")
for r in A3[:12]:
    print(f"| {nm(r['cfg'])} | {r['avg']:+.2f}% / {r['win']:.0f}% / **{r['pf']:.2f}** ({r['n']}) | "
          + " / ".join(f"{y}:{v:+.1f}%" for y, v, _ in r["per"]) + " |")

A4 = [r for r in A if r["win"] >= 60]
A4.sort(key=lambda r: -r["pf"])
print(f"\n## D. 승률 60%+ 중 PF 최상위 ({len(A4)}개 중 12)\n")
print("| 조건 | 순수익/승률/PF | 연도별 |\n|---|---|---|")
for r in A4[:12]:
    print(f"| {nm(r['cfg'])} | {r['avg']:+.2f}% / {r['win']:.0f}% / **{r['pf']:.2f}** ({r['n']}) | "
          + " / ".join(f"{y}:{v:+.1f}%" for y, v, _ in r["per"]) + " |")
