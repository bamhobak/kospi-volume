# -*- coding: utf-8 -*-
"""'가격이 죽은' 종목 걸러내기 — 자기 과거 대비 변동성(pinr)으로.

1차(us_n1_pinned.py)에서 **절대** 변동성으로 잘랐더니 걸린 게 KO·WMT·CMG 같은 대형 우량주였고
성적도 멀쩡했다(38건 · 평균 +2.68%). 가설이 틀린 게 아니라 **잣대가 틀렸다** —
대형주는 원래 조용하다. 인수 합의로 묶인 종목은 '**자기 평소보다**' 죽는다.

  pinr = 최근 20일 변동성 ÷ 최근 250일 변동성
    DV(합병 확정, 인수가 $13.60 에 고정) 0.06 — 유니버스 하위 0.4%
    PARR(정상 상승 추세)              1.01 — 74%
  여기에 20일 고저폭 5% 미만을 겹치면 4,424 종목 중 93개(2.1%)가 걸리는데,
  그 안에 **SPAC(합병 전 $10 고정)·우선주**도 같이 들어온다. 둘 다 모멘텀 규칙이 사면 안 되는 종목이다.

⚠ 백테스트의 한계: 인수가 **성사**된 회사는 상장폐지되며 패널에서 사라진다. 즉 과거 표본에는
   '딜이 깨졌거나 애초에 대상이 아니었던' 것만 남아 있어 이 필터의 값어치는 **과소평가**된다.
   그래도 "빼도 손해가 아니다" 만 확인되면 넣을 이유는 충분하다.

    python us_n1_pinned2.py
"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd, FinanceDataReader as fdr
from vp_lib import boot_ci

BASE = Path(__file__).parent; TR1, VA0 = "20221231", "20230101"
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
g = K.groupby("ticker", sort=False)
K["v250"] = g.close.transform(lambda s: s.pct_change().rolling(250).std() * 100)
K["pinr"] = K.vol20 / K.v250
K["hl20"] = (g.close.transform(lambda s: s.rolling(20).max())
             / g.close.transform(lambda s: s.rolling(20).min()) - 1) * 100
K["a20b"] = g.volume.transform(lambda s: s.shift(3).rolling(20).mean())
K["re_mo"] = K.vm3 / K.a20b * 100
_w = (K.fromhi >= -5).fillna(False)
_sn = (_w.groupby(K.ticker).shift(1).fillna(False).astype(bool)
       .groupby(K.ticker).transform(lambda s: s.rolling(20, min_periods=1).max()).fillna(0) > 0)
N1 = (UNI & UP & _w & ~_sn & (K.re_mo <= 100)).fillna(False)
# 자사주 낙폭(N4)도 같은 위험이 있나 — 낙폭 계열은 딜 픽스와 거리가 멀지만 확인은 한다
B = pd.read_pickle(BASE / "data/us/buyback.pkl")
SP = B[B.tag == "spend"].copy()
SP["days"] = (pd.to_datetime(SP.end, errors="coerce") - pd.to_datetime(SP.start, errors="coerce")).dt.days
SP = SP[(SP.days >= 60) & (SP.days <= 200) & (SP.val > 0)]
SP = SP.sort_values("days").drop_duplicates(["ticker", "filed"], keep="first")
SP = SP.rename(columns={"filed": "date"})[["ticker", "date", "val"]].rename(columns={"val": "bbv"})
K = K.merge(SP, on=["ticker", "date"], how="left")
g = K.groupby("ticker", sort=False)
K["sp60"] = g.bbv.transform(lambda s: s.rolling(60, min_periods=1).count()) > 0
PURE = ((K.fromhi <= -30) & K.sp60 & (K.ret20 <= -20)).fillna(False)
_s2 = (PURE.groupby(K.ticker).shift(1).fillna(False).astype(bool)
       .groupby(K.ticker).transform(lambda s: s.rolling(20, min_periods=1).max()).fillna(0) > 0)
N4 = (PURE & ~_s2 & UNI).fillna(False)
BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in (20, 40, 60)}
NDAY = len([d for d in ud if d >= "20160101"])
PIN = ((K.pinr < 0.4) & (K.hl20 < 5)).fillna(False)

def dd(cond, h=40):
    X = K[cond.fillna(False)].dropna(subset=[f"n{h}"]).sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i: continue
        last[t] = i + h; keep.append(ix)
    d = X.loc[keep].copy(); d = d[d.date >= "20160101"]
    d["r"] = d[f"n{h}"].astype(float); d["ex"] = d.r - d.date.map(BEN[h]); d["ym"] = d.date.str[:6]
    return d[d.r.notna()]

HDR = (f"  {'조건':<32} {'n':>6} {'일':>5} {'승률':>6} {'평균':>7} {'중앙':>7} {'절삭':>7} {'초과':>7} "
       f"{'학습':>7} {'검증':>7} {'학CI':>7} {'검CI':>7} {'연양수':>6}")
def show(tag, cond, h=40):
    d = dd(cond, h)
    if len(d) < 50: print(f"  {tag:<32} {len(d):>6}  (표본 부족 — 그만큼 드물다)"); return d
    tr = d[d.date <= TR1]; va = d[d.date >= VA0]
    cit = boot_ci(tr.groupby("ym").ex.mean()) if len(tr) >= 25 else np.nan
    civ = boot_ci(va.groupby("ym").ex.mean()) if len(va) >= 25 else np.nan
    yr = d.groupby(d.date.str[:4]).ex.mean(); trim = d.r[d.r <= d.r.quantile(0.95)].mean()
    print(f"  {tag:<32} {len(d):>6} {len(d)/NDAY:>5.2f} {(d.r>0).mean()*100:>5.1f}% {d.r.mean():>7.2f} "
          f"{d.r.median():>7.2f} {trim:>7.2f} {d.ex.mean():>7.2f} {tr.ex.mean():>7.2f} {va.ex.mean():>7.2f} "
          f"{cit:>7.2f} {civ:>7.2f} {int((yr>0).sum()):>3}/{len(yr)}")
    return d

Z = dd(N1)
Zp = Z.drop(columns=[c for c in ("pinr", "hl20") if c in Z.columns]).merge(
    K[["ticker", "date", "pinr", "hl20"]], on=["ticker", "date"], how="left")
print(f"[상승장 신고가] 실거래 {len(Z):,}건 중 '가격이 죽은' 것 "
      f"{int(((Zp.pinr<0.4)&(Zp.hl20<5)).sum())}건 "
      f"({((Zp.pinr<0.4)&(Zp.hl20<5)).mean()*100:.1f}%)")
print("\n" + "=" * 152); print("① 문턱별 — 걸린 쪽 vs 뺀 쪽 (40일)"); print("=" * 152); print(HDR)
for pr, hl in ((0.2, 5), (0.3, 5), (0.4, 5), (0.4, 8), (0.5, 8)):
    show(f"  pinr<{pr} & 고저폭<{hl}% 만", N1 & (K.pinr < pr) & (K.hl20 < hl))
print()
for pr, hl in ((0.2, 5), (0.3, 5), (0.4, 5), (0.4, 8), (0.5, 8)):
    show(f"  pinr<{pr} & 고저폭<{hl}% 제외", N1 & ~((K.pinr < pr) & (K.hl20 < hl)))
print()
show("원본 (제외 없음)", N1)
print("\n" + "=" * 152); print("② [자사주 낙폭](N4)도 같은 위험이 있나 (60일)"); print("=" * 152); print(HDR)
show("N4 원본", N4, h=60)
show("N4 · pinr<0.4&고저폭<5% 제외", N4 & ~PIN, h=60)
print("\n" + "=" * 152); print("③ 걸린 종목들은 실제로 뭐였나"); print("=" * 152)
P = dd(N1 & PIN)
if len(P):
    Pm = P.drop(columns=[c for c in ("pinr",) if c in P.columns]).merge(
        K[["ticker", "date", "pinr"]], on=["ticker", "date"], how="left")
    print(f"  {len(P)}건 · 평균 {P.r.mean():+.2f}% · 중앙 {P.r.median():+.2f}% · 승률 {(P.r>0).mean()*100:.1f}%")
    print(f"  ±2% 안에서 끝난 비율 {(P.r.abs()<=2).mean()*100:.1f}% · -10% 아래 {(P.r<=-10).mean()*100:.1f}%")
    print("  사례: " + ", ".join(f"{t}({r:+.0f}%)" for t, r in zip(Pm.ticker.tail(14), Pm.r.tail(14))))
try:
    import verdict; verdict.log_trials("us_n1_pinned", 12)
except Exception as e: print(e)
