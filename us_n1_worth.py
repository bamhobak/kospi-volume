# -*- coding: utf-8 -*-
"""[상승장 신고가]가 자기 자리값을 하나 — N4 가 생긴 지금 다시 묻는다.

사용자 질문: "n1은 너가 봐도 좀 별로지?"
규칙 단위로는 넷 중 가장 약하다 — 상위5% 절삭평균 -0.38(음수), 스트레스(2005~15) 초과 -0.04,
학습 월CI -0.08, 생존편향이 유일하게 **부풀리는** 방향(신고가 계열). 개선 시도도 60여 셀 전량 기각.

그러나 '약하다' 와 '빼야 한다' 는 다른 질문이다.
  · N1 은 미장 4규칙 중 **유일한 상승장 규칙**이다. 나머지 셋은 전부 낙폭 계열이라
    지수가 오르는 동안 잠들어 있다. 그 구간을 N1 이 메운다.
  · 지금 N1 은 **자리 8개**로 넷 중 가장 많이 차지한다(나머지는 각 3).
그래서 계좌로 직접 묻는다 — 넣는 게 나은가, 뺀 게 나은가, 자리를 줄이는 게 나은가.

⚠ 지수와 견주지 않는다. 사용자 기준은 '지수를 이기는 것' 이 아니라
   '오를 때 적당히, 내릴 때 안전하게' 다([[goal-not-beating-index]]).
   그래서 최종 판정은 계좌의 **최악 시드·낙폭·제자리 기간**까지 함께 본다.

    python us_n1_worth.py
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
N1 = (UNI & UP & _w & ~_seen & (K.re_mo <= 100)).fillna(False)
PURE = ((K.fromhi <= -30) & K.sp60 & (K.ret20 <= -20)).fillna(False)
_s2 = (PURE.groupby(K.ticker).shift(1).fillna(False).astype(bool)
       .groupby(K.ticker).transform(lambda s: s.rolling(20, min_periods=1).max()).fillna(0) > 0)
N4 = (PURE & ~_s2 & UNI).fillna(False)
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

TAB = {"D1": tb(D1c, 20), "D2": tb(D2c, 40), "N1": tb(N1, 40), "N4": tb(N4, 60)}

def build(parts):
    return pd.concat([TAB[r].assign(rid=r, pct=p, mx=m) for r, p, m in parts],
                     ignore_index=True).sort_values("di").reset_index(drop=True)

def sim(S, ds, seed=None):
    rng = np.random.default_rng(seed) if seed is not None else None
    nav, held, cnt = 1.0, {}, {}
    peak, mdd, inv, curve = 1.0, 0.0, [], []
    byd = {d: gg for d, gg in S[S.date.isin(set(ds))].groupby("date")}
    for d in ds:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            nav *= 1 + held.pop(k)[1] / 100; cnt[k[0]] = cnt.get(k[0], 0) - 1
        peak = max(peak, nav); mdd = min(mdd, nav / peak - 1)
        inv.append(sum(x[3] for x in held.values())); curve.append(nav)
        gg = byd.get(d)
        if gg is None: continue
        gg = (gg.sample(frac=1, random_state=int(rng.integers(1 << 30))) if rng is not None
              else gg.sort_values("amt20", ascending=False, na_position="last"))
        for r_ in gg.itertuples():
            if cnt.get(r_.rid, 0) >= r_.mx: continue
            k = (r_.rid, r_.ticker, d)
            if k in held or sum(x[3] for x in held.values()) + r_.pct / 100 > 1.0: continue
            held[k] = (di + int(r_.hold), r_.ret * r_.pct / 100, r_.rid, r_.pct / 100)
            cnt[r_.rid] = cnt.get(r_.rid, 0) + 1
    for v in held.values(): nav *= 1 + v[1] / 100
    c = pd.Series(curve)
    flat = run_ = 0
    for x in (c / c.cummax() - 1).values:
        run_ = run_ + 1 if x < -0.005 else 0
        flat = max(flat, run_)
    return nav, mdd * 100, float(np.mean(inv)), flat / 252

PER = [("학습", "20160101", "20221231"), ("검증", "20230101", "20991231"), ("기준", "20160101", "20991231")]
DS = {p[0]: [d for d in ud if p[1] <= d <= p[2]] for p in PER}
HD = (f"  {'구성':<30}{'학습':>10}{'검증':>10}{'기준':>10}{'낙폭':>7}{'투입':>6}{'제자리':>7}"
      f"{'랜중앙':>10}{'랜최악':>10}{'랜낙폭':>8}")
def row(nm, parts):
    S = build(parts)
    res = [sim(S, DS[p[0]]) for p in PER]
    R = [sim(S, DS["기준"], seed=k) for k in range(30)]
    nav = np.array([x[0] for x in R]); dd_ = np.array([x[1] for x in R])
    print(f"  {nm:<30}" + "".join(f"{x[0]:>9.2f}배" for x in res)
          + f"{res[2][1]:>6.0f}%{res[2][2]*100:>6.0f}%{res[2][3]:>6.1f}년"
          + f"{np.median(nav):>9.2f}배{nav.min():>9.2f}배{np.median(dd_):>7.0f}%", flush=True)

print("\n" + "=" * 130)
print("[상승장 신고가]가 자기 자리값을 하나 — 넣고/빼고/줄여서 계좌로 비교 (30시드)")
print("=" * 130)
print(HD)
D = [("D1", 5, 3), ("D2", 5, 3)]
row("낙폭 둘만 (N1·N4 없음)", D)
row("+ N1 자리8 (현행)", D + [("N1", 5, 8)])
row("+ N4 자리3", D + [("N4", 5, 3)])
print()
row("+ N1 자리8 + N4 자리3", D + [("N1", 5, 8), ("N4", 5, 3)])
row("+ N1 자리6 + N4 자리3", D + [("N1", 5, 6), ("N4", 5, 3)])
row("+ N1 자리4 + N4 자리3", D + [("N1", 5, 4), ("N4", 5, 3)])
row("+ N1 자리2 + N4 자리3", D + [("N1", 5, 2), ("N4", 5, 3)])
row("+ N4 자리3 (N1 뺌)", D + [("N4", 5, 3)])
print()
row("+ N1 자리8 + N4 자리5", D + [("N1", 5, 8), ("N4", 5, 5)])
row("+ N1 자리4 + N4 자리5", D + [("N1", 5, 4), ("N4", 5, 5)])

# 상승 국면에서 실제로 무엇이 일하나 — N1 이 메운다는 자리가 진짜인지
print("\n" + "=" * 130)
print("국면별 거래 분포 — N1 을 빼면 상승 국면이 비는가")
print("=" * 130)
for rid in ("D1", "D2", "N1", "N4"):
    t = TAB[rid].copy()
    t["up"] = t.date.map(dict(zip(K.date, K.ixup))).fillna(False)
    print(f"  {rid}: 거래 {len(t):>5}건 · 상승국면 {t.up.mean()*100:>4.0f}% · "
          f"평균 {t.ret.mean():>+6.2f}% · 중앙 {t.ret.median():>+6.2f}%")
