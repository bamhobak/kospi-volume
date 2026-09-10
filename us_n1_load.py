# -*- coding: utf-8 -*-
"""운용 부담 — 실제로 몇 종목을 동시에 들고, 한 달에 몇 번 사고파는가. 그리고 줄일 수 있는가.

사용자 지적: "수익률도 수익률이지만 그 많은 종목을 사서 40일 동안 다 가지고 있는 게 별로야."
맞는 지적이고, 이건 수익률과 **다른 축**이라 따로 재야 한다.

앞서 잰 '자리4' 는 종목당 비중을 5% 로 둔 채라 **노출까지 같이 줄어** 손해로 나왔다.
제대로 된 질문은 이것이다 — **노출을 그대로 두고 종목 수만 줄이면 얼마를 잃는가?**
  자리8 × 5%  = 최대 40%  (현행 · 관리 8종목)
  자리4 × 10% = 최대 40%  (관리 4종목)
  자리2 × 20% = 최대 40%  (관리 2종목)
집중하면 한 종목이 틀렸을 때 계좌가 더 아프다. 그래서 **최악 시드·낙폭·한 종목 최대손실**을
같이 본다. 보유일도 함께 흔든다(40일이 길다는 것도 부담의 절반이다).

    python us_n1_load.py
"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd, FinanceDataReader as fdr

BASE = Path(__file__).parent
B = pd.read_pickle(BASE / "data/us/buyback.pkl")
K = pd.read_pickle(BASE / "data/us_scan.pkl")
K = K[((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
IX = fdr.DataReader("US500", "2004-06-01"); IX = IX[IX.Close > 0].copy()
IX["date"] = IX.index.strftime("%Y%m%d"); IX["ma60"] = IX.Close.rolling(60).mean()
K["ixup"] = K.date.map(dict(zip(IX.date, IX.Close > IX.ma60)))
ud = sorted(K.date.unique()); ADI = {d: i for i, d in enumerate(ud)}
K["di"] = K.date.map(ADI).astype(np.int32)
K["amt_q"] = K.groupby("date").amt20.rank(pct=True)
UNI = (K.amt_q >= 0.6).fillna(False); UP = K.ixup == True; DN = K.ixup == False
SP = B[B.tag == "spend"].copy()
SP["days"] = (pd.to_datetime(SP.end, errors="coerce") - pd.to_datetime(SP.start, errors="coerce")).dt.days
SP = SP[(SP.days >= 60) & (SP.days <= 200) & (SP.val > 0)]
SP = SP.sort_values("days").drop_duplicates(["ticker", "filed"], keep="first")
SP = SP.rename(columns={"filed": "date"})[["ticker", "date", "val"]].rename(columns={"val": "bbspend"})
K = K.merge(SP, on=["ticker", "date"], how="left")
g = K.groupby("ticker", sort=False)
K["sp60"] = g.bbspend.transform(lambda s: s.rolling(60, min_periods=1).count()) > 0
K["a20b"] = g.volume.transform(lambda s: s.shift(3).rolling(20).mean())
K["re_mo"] = K.vm3 / K.a20b * 100
_w = (K.fromhi >= -5).fillna(False)
_seen = (_w.groupby(K.ticker).shift(1).fillna(False).astype(bool)
         .groupby(K.ticker).transform(lambda s: s.rolling(20, min_periods=1).max()).fillna(0) > 0)
N1S = (UNI & UP & _w & ~_seen & (K.re_mo <= 100)).fillna(False)
PURE = ((K.fromhi <= -30) & K.sp60 & (K.ret20 <= -20)).fillna(False)
_s2 = (PURE.groupby(K.ticker).shift(1).fillna(False).astype(bool)
       .groupby(K.ticker).transform(lambda s: s.rolling(20, min_periods=1).max()).fillna(0) > 0)
N4S = (PURE & ~_s2 & UNI).fillna(False)
U2 = K.amt20.fillna(0) >= 2.0
DEBT = K["부채비율"] if "부채비율" in K.columns else pd.Series(np.nan, index=K.index)
D1c = (U2 & DN & (K.ret20 <= -30) & (K.su1 >= 2) & (K.u <= -10)
       & (DEBT.isna() | (DEBT <= 200))).fillna(False)
D2c = (U2 & DN & (K.PBR > 0) & (K.PBR <= 0.8) & (K.ret20 <= -10) & (K.su1 >= 2) & (K.u <= -10)).fillna(False)

def tb(cond, h):
    X = K[cond.fillna(False)].dropna(subset=[f"n{h}"]).sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i: continue
        last[t] = i + h; keep.append(ix)
    d = X.loc[keep].copy(); d = d[(d.date >= "20160101") & (d.buy > 0)]
    d["ret"] = d[f"n{h}"].astype(float); d["hold"] = h
    return d[["date", "ticker", "hold", "ret", "di", "amt20"]]

CACHE = {}
def T(rid, cond, h):
    if (rid, h) not in CACHE: CACHE[(rid, h)] = tb(cond, h)
    return CACHE[(rid, h)]

def sim(parts, ds, seed=None):
    """parts: [(rid, cond, hold, pct, max), ...]  반환에 운용 부담 지표를 함께 담는다."""
    S = pd.concat([T(r, c, h).assign(rid=r, pct=p, mx=m) for r, c, h, p, m in parts],
                  ignore_index=True).sort_values("di").reset_index(drop=True)
    rng = np.random.default_rng(seed) if seed is not None else None
    nav, held, cnt = 1.0, {}, {}
    peak, mdd = 1.0, 0.0
    npos, buys, sells, worst = [], 0, 0, 0.0
    byd = {d: gg for d, gg in S[S.date.isin(set(ds))].groupby("date")}
    for d in ds:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            v = held.pop(k); nav *= 1 + v[1] / 100; cnt[k[0]] = cnt.get(k[0], 0) - 1
            sells += 1; worst = min(worst, v[4])
        peak = max(peak, nav); mdd = min(mdd, nav / peak - 1)
        gg = byd.get(d)
        if gg is not None:
            gg = (gg.sample(frac=1, random_state=int(rng.integers(1 << 30))) if rng is not None
                  else gg.sort_values("amt20", ascending=False, na_position="last"))
            for r_ in gg.itertuples():
                if cnt.get(r_.rid, 0) >= r_.mx: continue
                k = (r_.rid, r_.ticker, d)
                if k in held or sum(x[3] for x in held.values()) + r_.pct / 100 > 1.0: continue
                held[k] = (di + int(r_.hold), r_.ret * r_.pct / 100, r_.rid, r_.pct / 100, r_.ret)
                cnt[r_.rid] = cnt.get(r_.rid, 0) + 1; buys += 1
        npos.append(len(held))
    for v in held.values(): nav *= 1 + v[1] / 100
    mon = len(ds) / 21
    return dict(nav=nav, mdd=mdd * 100, avg=float(np.mean(npos)), mx=int(np.max(npos)),
                buy=buys / mon, sell=sells / mon, worst=worst)

PER = [("학습", "20160101", "20221231"), ("검증", "20230101", "20991231"), ("기준", "20160101", "20991231")]
DS = {p[0]: [d for d in ud if p[1] <= d <= p[2]] for p in PER}
D = [("D1", D1c, 20, 5, 3), ("D2", D2c, 40, 5, 3)]

HD = (f"  {'구성':<28}{'기준':>9}{'검증':>9}{'낙폭':>7}{'동시보유':>9}{'최대':>6}"
      f"{'월매수':>7}{'월매도':>7}{'한종목최악':>10}{'랜중앙':>9}{'랜최악':>9}")
def row(nm, parts):
    r0 = sim(parts, DS["기준"]); rv = sim(parts, DS["검증"])
    R = [sim(parts, DS["기준"], seed=k)["nav"] for k in range(30)]
    R = np.array(R)
    print(f"  {nm:<28}{r0['nav']:>8.2f}배{rv['nav']:>8.2f}배{r0['mdd']:>6.0f}%"
          f"{r0['avg']:>8.1f}개{r0['mx']:>5}개{r0['buy']:>6.1f}회{r0['sell']:>6.1f}회"
          f"{r0['worst']:>9.1f}%{np.median(R):>8.2f}배{R.min():>8.2f}배", flush=True)

print("\n" + "=" * 140)
print("① 지금 실제 부담 — 몇 종목을 동시에 들고 한 달에 몇 번 사고파나")
print("=" * 140)
print(HD)
row("현행 (N1 자리8×5%)", D + [("N1", N1S, 40, 5, 8), ("N4", N4S, 60, 5, 3)])
print()
print("=" * 140)
print("② 노출은 그대로, 종목 수만 줄이면 (N1 최대 40% 고정)")
print("=" * 140)
print(HD)
for mx, pct in ((8, 5), (6, 6.7), (5, 8), (4, 10), (3, 13.3), (2, 20)):
    row(f"  N1 자리{mx}×{pct}% (최대 {mx*pct:.0f}%)", D + [("N1", N1S, 40, pct, mx), ("N4", N4S, 60, 5, 3)])
print()
print("=" * 140)
print("③ 보유일도 같이 줄이면 (자리4×10%)")
print("=" * 140)
print(HD)
for h in (10, 20, 40):   # 30일은 패널에 n30 이 없다
    row(f"  N1 {h}일 보유 · 자리4×10%", D + [("N1", N1S, h, 10, 4), ("N4", N4S, 60, 5, 3)])
print()
print("=" * 140)
print("④ N4 도 같이 (자리3×5% → 자리2×7.5%)")
print("=" * 140)
print(HD)
row("  N1 4×10% · N4 3×5%", D + [("N1", N1S, 40, 10, 4), ("N4", N4S, 60, 5, 3)])
row("  N1 4×10% · N4 2×7.5%", D + [("N1", N1S, 40, 10, 4), ("N4", N4S, 60, 7.5, 2)])
row("  N1 3×13.3% · N4 2×7.5%", D + [("N1", N1S, 40, 13.3, 3), ("N4", N4S, 60, 7.5, 2)])
row("  전부 집중 (D도 2×7.5%)",
    [("D1", D1c, 20, 7.5, 2), ("D2", D2c, 40, 7.5, 2), ("N1", N1S, 40, 10, 4), ("N4", N4S, 60, 7.5, 2)])
