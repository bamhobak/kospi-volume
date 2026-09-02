# -*- coding: utf-8 -*-
"""[자사주 낙폭] 을 코스피·코스닥으로 나눠 각각 더 나은 조건이 있는지 실측.

지금은 두 시장에 같은 조건을 쓴다(자사주 직접취득 공시 + 60일 -20% + 코스피 60일선 아래).
시장 성격이 다르니 따로 조이면 나아질 수 있다. 학습(2018~22)에서만 후보를 고르고
검증(2023~)은 확인용으로만 본다.

메모리 주의: 패널이 1.3GB 라 필요한 컬럼만 읽고, 시장 하나씩 처리한 뒤 즉시 해제한다
(전체를 올렸다가 페이지파일이 HDD 라 시스템이 멈춘 적이 있다).
"""
import io, sys, gc, sqlite3
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
HOLD = 10

IX = fdr.DataReader("KS11", "2017-01-01"); IX = IX[IX.Close > 0].copy()
IX["date"] = IX.index.strftime("%Y%m%d")
UP60 = dict(zip(IX.date, IX.Close > IX.Close.rolling(60).mean()))
del IX; gc.collect()

con = sqlite3.connect(BASE / "data/dart/disclosures.db")
D = pd.read_sql("SELECT stock_code AS ticker, rcept_dt AS dt, report_nm FROM disclosure "
                "WHERE length(stock_code)=6 AND rcept_dt>='20180101' "
                "AND report_nm LIKE '%자기주식취득결정%'", con); con.close()
nm = D.report_nm.str.replace(" ", "", regex=False)
BB = set(zip(*D[~nm.str.contains("신탁") & ~nm.str.contains("정정")][["ticker", "dt"]].values.T))
del D, nm; gc.collect()

COLS = ["ticker", "date", "close", "ret20", "ret60", "ret120", "amt20", "marcap", "dil",
        "n10", "buy", "cost", "fw5", "fw20", "fw60", "ow20", "ow60", "PBR", "vol20",
        "dma20", "dma60", "mdd60", "su1", "clv", "u", "srd", "r16", "fromhi", "fromlo", "sr20"]
FEATS = ["ret20", "ret60", "ret120", "amt20", "marcap", "fw5", "fw20", "fw60", "ow20", "ow60",
         "PBR", "vol20", "dma20", "dma60", "mdd60", "su1", "clv", "u", "r16", "fromhi", "fromlo", "sr20"]

def boot(v, k, seed=127, n=2000):
    if len(v) < 20: return None
    rng = np.random.default_rng(seed)
    d = pd.DataFrame({"r": np.asarray(v), "ym": np.asarray(k)})
    by = {m: gg.r.to_numpy() for m, gg in d.groupby("ym")}; ms = list(by)
    if len(ms) < 3: return None
    return np.percentile([np.concatenate([by[x] for x in rng.choice(ms, len(ms), replace=True)]).mean()
                          for _ in range(n)], [2.5, 97.5])

def prep(f, mk):
    K = pd.read_pickle(BASE / "data" / f)
    K = K[[c for c in COLS if c in K.columns]].copy()
    K["mk"] = mk
    K["pref"] = ~K.ticker.str.endswith("0")
    K.loc[K.marcap / 1e4 > 2000, "marcap"] = np.nan
    K["bb"] = [(t, d) in BB for t, d in zip(K.ticker, K.date)]
    K["dn60"] = K.date.map(UP60).fillna(True) == False
    K["yr"] = K.date.str[:4]
    d = sorted(K.date.unique()); K["di"] = K.date.map({x: i for i, x in enumerate(d)})
    return K

def dedup(S):
    S = S.sort_values("di"); keep, last = [], {}
    for t, i, ix in zip(S.ticker.values, S.di.values, S.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i + HOLD; keep.append(ix)
    return S.loc[keep]

HDR = (f"  {'조건':<26} {'n':>4} {'평균':>7} {'승률':>5} {'중앙':>7} {'상5뺀':>7} "
       f"{'IS':>7} {'OS':>7} {'양수년':>5} {'학습CI':>13}")
def rep(S, tag, quiet=False):
    Z = dedup(S)
    if len(Z) < 25:
        if not quiet: print(f"  {tag:<26} {len(Z):>4} (부족)")
        return None
    zi, zo = Z[Z.date < "20230101"], Z[Z.date >= "20230101"]
    ci = boot(zi.r.values, zi.date.str[:6])
    cut = np.percentile(Z.r.values, 95); t5 = Z.r.values[Z.r.values <= cut].mean()
    med = float(np.median(Z.r)); yrs = Z.groupby("yr").r.mean()
    lo = ci[0] if ci is not None else np.nan
    ok = (lo > 0) and (med > 0) and (t5 > 0) and (len(zo) and zo.r.mean() > 0)
    f = f"[{ci[0]:+.1f},{ci[1]:+.1f}]" if ci is not None else "-"
    if not quiet:
        print(f"  {tag:<26} {len(Z):>4} {Z.r.mean():>+7.2f} {(Z.r>0).mean()*100:>4.0f}% {med:>+7.2f} "
              f"{t5:>+7.2f} {zi.r.mean():>+7.2f} {zo.r.mean() if len(zo) else float('nan'):>+7.2f} "
              f"{int((yrs>0).sum())}/{len(yrs):<2} {f:>13}{'  ✅' if ok else ''}")
    return dict(n=len(Z), r=Z.r.mean(), win=(Z.r > 0).mean()*100, IS=zi.r.mean(),
                OS=zo.r.mean() if len(zo) else np.nan, ok=ok)

for f, mk in (("kp_ow.pkl", "코스피"), ("kq_ow.pkl", "코스닥")):
    K = prep(f, mk)
    BASEC = ((~K.pref) & (~K.dil.fillna(False)) & (K.amt20.fillna(0) >= 3)
             & K.bb & (K.ret60 <= -20) & K.dn60)
    S0 = K[BASEC.fillna(False)].dropna(subset=["n10"]).copy()
    S0["r"] = S0.n10
    print(f"\n{'='*128}\n#### [자사주 낙폭] {mk} — 10일 보유 · 손절 없음\n{'='*128}")
    print(f"## 0) 현재 조건\n{HDR}")
    base = rep(S0, "현재(공통 조건)")
    if base is None:
        del K, S0; gc.collect(); continue
    Z = dedup(S0); IS = Z[Z.date < "20230101"]
    yr = Z.groupby("yr").r.agg(["mean", "size"])
    print("  연도별: " + " ".join(f"{i}:{r['mean']:+.0f}%({int(r['size'])})" for i, r in yr.iterrows()))

    print(f"\n## 1) 학습구간({len(IS)}건) 피처 4분위 — 검증은 보지 않음")
    print(f"  {'피처':<9} {'Q1':>8} {'Q2':>8} {'Q3':>8} {'Q4':>8} {'Q4-Q1':>8} {'단조':>4}")
    cand = []
    for ft in FEATS:
        if ft not in IS.columns: continue
        v = IS[ft].dropna()
        if len(v) < 30 or v.nunique() < 8: continue
        try: q = pd.qcut(IS[ft], 4, labels=False, duplicates="drop")
        except Exception: continue
        if pd.Series(q).nunique() < 4: continue
        ms = [IS.r[q == i].mean() for i in range(4)]
        if min(int((q == i).sum()) for i in range(4)) < 6: continue
        diff = ms[3] - ms[0]
        mono = "↑" if ms[0] < ms[1] < ms[2] < ms[3] else ("↓" if ms[0] > ms[1] > ms[2] > ms[3] else "")
        print(f"  {ft:<9} {ms[0]:>+8.2f} {ms[1]:>+8.2f} {ms[2]:>+8.2f} {ms[3]:>+8.2f} {diff:>+8.2f} {mono:>4}")
        if abs(diff) >= 6.0:
            cand.append((ft, diff, pd.qcut(IS[ft], 4, retbins=True, duplicates="drop")[1]))
    cand.sort(key=lambda x: -abs(x[1]))
    print(f"  → 격차 6%p↑ 후보: {[c[0] for c in cand] or '없음'}")

    print(f"\n## 2) 문턱 조이기\n{HDR}")
    TR = {"낙폭 ret60≤-30": S0.ret60 <= -30, "낙폭 ret60≤-40": S0.ret60 <= -40,
          "거래대금 ≥10억": S0.amt20 >= 10, "거래대금 ≥30억": S0.amt20 >= 30,
          "시총 ≥1천억": S0.marcap >= 1000, "시총 ≥3천억": S0.marcap >= 3000,
          "외인 fw60≥0": S0.fw60 >= 0, "기관 ow20≥0": S0.ow20 >= 0,
          "업종 u≤-10": S0.u <= -10, "업종 u≤-20": S0.u <= -20,
          "공매도감소 srd": S0.srd == True, "저PBR ≤1": S0.PBR <= 1}
    pool = {}
    for t, c in TR.items():
        r = rep(S0[c.fillna(False)], t)
        if r: pool[t] = (r, c)
    if cand:
        print(f"\n## 3) 학습에서 고른 새 조건\n{HDR}")
        for ft, diff, ed in cand[:5]:
            th = ed[2]
            c, t = (S0[ft] >= th, f"{ft} ≥ {th:.2f}") if diff > 0 else (S0[ft] < th, f"{ft} < {th:.2f}")
            if t in pool: continue
            r = rep(S0[c.fillna(False)], t)
            if r: pool[t] = (r, c)
    good = sorted([(k, v) for k, v in pool.items() if v[0]["IS"] > base["IS"] and v[0]["n"] >= 30],
                  key=lambda x: -x[1][0]["IS"])[:4]
    if len(good) >= 2:
        import itertools
        print(f"\n## 4) 학습에서 개선된 것끼리 2개 조합\n{HDR}")
        for (n1, (r1, c1)), (n2, (r2, c2)) in itertools.combinations(good, 2):
            rep(S0[(c1 & c2).fillna(False)], f"{n1} + {n2}"[:26])
    del K, S0, Z, IS; gc.collect()

print("\n※ 학습에서 좋아도 검증(OS)에서 무너지면 과적합이다.")
print("  시장별로 다른 조건을 쓰려면 양쪽 다 검증에서 버텨야 한다.")
