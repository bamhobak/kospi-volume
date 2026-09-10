# -*- coding: utf-8 -*-
"""상승장 2호 후보 마지막 실마리 — 내부자 매수 공시(사건).

앞선 두 단계에서 걸러진 것:
  · 가격 축은 한 덩어리라 이미 [상승장 신고가](N1)가 됐다 — 같은 걸 또 파면 사촌만 나온다.
  · 재무 기반 비가격 축(흑자·저PBR·자사주 집행·EPS 성장)은 십분위로는 ρ +0.86~+0.99 로
    깨끗했는데, **기준선을 같은 부분집합으로 맞추자 전부 사라졌다**(자사주 +0.41 → -0.06).
    '재무를 보고하는 회사가 원래 좋다' 를 보고 있었던 것이다([[backtest-pitfalls]] 4번).

남은 하나: **내부자 장내매수 공시 + 상승장**. 앞서 잰 칸 하나가 유일하게 CI 양쪽 양수였다
  (금액 100만$↑ · 상승장 · 20일 보유 — 초과 +1.49 · 학CI +0.24 · 검CI +0.50 · 양수해 10/11).
이건 **상태가 아니라 사건**(그날 공시)이라 부분집합 편향이 약하다. 그래도 확인은 한다.

기준선 셋을 나란히 낸다.
  전체      그날 상승국면 유니버스 평균
  내부자활동 그날 **어떤 형태로든 내부자 신고가 있었던 종목들** 평균 ← 부분집합 통제
  매도      그날 내부자 **매도** 공시가 있었던 종목들 평균 ← 방향 통제(사는 게 파는 것보다 나은가)

⚠ 약점을 미리 적어 둔다: 상위5% 절삭평균이 -0.17(음수)이고 스트레스(2006~15) 초과가 -0.13 이다.
   N1 과 같은 약점이라, 이걸 못 고치면 'N1 의 사촌' 이지 대안이 아니다.

    python us_bull5.py
"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd, FinanceDataReader as fdr
from vp_lib import boot_ci

BASE = Path(__file__).parent; TR1, VA0 = "20221231", "20230101"
A = pd.read_pickle(BASE / "data/us/insider_all.pkl")
A = A[(A.form == "4") & (A.price > 0) & (A.val > 0) & (A.val < 1e8)]
BUY = A[A.code == "P"].groupby(["ticker", "fdate"]).agg(bv=("val", "sum"), bn=("acc", "nunique"))
SELL = A[A.code == "S"].groupby(["ticker", "fdate"]).agg(sv=("val", "sum"))
ANY = A.groupby(["ticker", "fdate"]).size().rename("anyf")
K = pd.read_pickle(BASE / "data/us_scan.pkl")
K = K[((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
for df, nm in ((BUY, None), (SELL, None), (ANY.to_frame(), None)):
    df.index.names = ["ticker", "date"]
K = K.merge(BUY.reset_index(), on=["ticker", "date"], how="left") \
     .merge(SELL.reset_index(), on=["ticker", "date"], how="left") \
     .merge(ANY.reset_index(), on=["ticker", "date"], how="left")
IX = fdr.DataReader("US500", "2004-06-01"); IX = IX[IX.Close > 0].copy()
IX["date"] = IX.index.strftime("%Y%m%d"); IX["ma60"] = IX.Close.rolling(60).mean()
K["ixup"] = K.date.map(dict(zip(IX.date, IX.Close > IX.ma60)))
ud = sorted(K.date.unique()); ADI = {d: i for i, d in enumerate(ud)}
K["di"] = K.date.map(ADI).astype(np.int32)
K["amt_q"] = K.groupby("date").amt20.rank(pct=True)
UNI = (K.amt_q >= 0.6).fillna(False); UP = K.ixup == True
BASEC = (UNI & UP).fillna(False)
NDAY = len([d for d in ud if d >= "20160101"])

BENS = {}
for h in (20, 40, 60):
    BENS[("all", h)] = K[BASEC].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean()
    BENS[("act", h)] = K[BASEC & K.anyf.notna()].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean()
    BENS[("sell", h)] = K[BASEC & K.sv.notna()].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean()
print(f"상승국면 하루 {int(BASEC.sum())/NDAY:,.0f}종목 · 내부자 신고 있는 날 "
      f"{int((BASEC & K.anyf.notna()).sum())/NDAY:,.1f} · 매수 {int((BASEC & K.bv.notna()).sum())/NDAY:,.1f} · "
      f"매도 {int((BASEC & K.sv.notna()).sum())/NDAY:,.1f}")

def dd(cond, h, lo="20160101", hi="20991231"):
    X = K[cond.fillna(False)].dropna(subset=[f"n{h}"]).sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i: continue
        last[t] = i + h; keep.append(ix)
    d = X.loc[keep].copy(); d = d[(d.date >= lo) & (d.date <= hi)]
    d["r"] = d[f"n{h}"].astype(float); d["ym"] = d.date.str[:6]
    return d[d.r.notna()]

HDR = (f"  {'조건':<28} {'n':>6} {'일':>5} {'승률':>6} {'중앙':>7} {'절삭':>7} "
       f"{'초과(전체)':>10} {'vs내부자활동':>12} {'vs매도':>8} {'학습':>7} {'검증':>7} {'학CI':>7} {'검CI':>7} {'연양수':>6}")
def show(tag, cond, h=20, lo="20160101", hi="20991231"):
    d = dd(cond, h, lo, hi)
    if len(d) < 60: print(f"  {tag:<28} {len(d):>6}  (표본 부족)"); return d
    d["exA"] = d.r - d.date.map(BENS[("all", h)])
    d["ex"] = d.r - d.date.map(BENS[("act", h)])
    d["exS"] = d.r - d.date.map(BENS[("sell", h)])
    tr = d[d.date <= TR1]; va = d[(d.date >= VA0) & (d.date <= hi)]
    cit = boot_ci(tr.groupby("ym").ex.mean()) if len(tr) >= 25 else np.nan
    civ = boot_ci(va.groupby("ym").ex.mean()) if len(va) >= 25 else np.nan
    yr = d.groupby(d.date.str[:4]).ex.mean(); trim = d.r[d.r <= d.r.quantile(0.95)].mean()
    print(f"  {tag:<28} {len(d):>6} {len(d)/NDAY:>5.2f} {(d.r>0).mean()*100:>5.1f}% {d.r.median():>7.2f} "
          f"{trim:>7.2f} {d.exA.mean():>10.2f} {d.ex.mean():>12.2f} {d.exS.mean():>8.2f} "
          f"{tr.ex.mean():>7.2f} {va.ex.mean():>7.2f} {cit:>7.2f} {civ:>7.2f} {int((yr>0).sum()):>3}/{len(yr)}")
    return d

print("\n" + "=" * 168); print("① 기준선 셋으로 다시 — 부분집합 편향이 있나 (20일 보유)"); print("=" * 168)
print(HDR)
show("내부자 매수 공시", BASEC & K.bv.notna())
for v in (1e5, 3e5, 1e6, 2e6):
    show(f"  매수액 {v/1e6:.1f}M$ 이상", BASEC & (K.bv >= v))
show("  신고 2건 이상", BASEC & (K.bn >= 2))
show("  매수 & 같은날 매도 없음", BASEC & K.bv.notna() & K.sv.isna())
print()
show("(대조) 내부자 매도 공시", BASEC & K.sv.notna())

print("\n" + "=" * 168); print("② 보유일"); print("=" * 168); print(HDR)
for h in (20, 40, 60):
    show(f"  100만$↑ · {h}일", BASEC & (K.bv >= 1e6), h=h)

print("\n" + "=" * 168); print("③ 스트레스 2006~2015"); print("=" * 168); print(HDR)
for h in (20, 40):
    show(f"  100만$↑ · {h}일 · 06~15", BASEC & (K.bv >= 1e6), h=h, lo="20060101", hi="20151231")

print("\n" + "=" * 168); print("④ 복권형·연도별 (100만$↑ · 20일)"); print("=" * 168)
d = dd(BASEC & (K.bv >= 1e6), 20)
d["ex"] = d.r - d.date.map(BENS[("act", 20)])
tot = d.r.sum()
print(f"  승률 {(d.r>0).mean()*100:.1f}% · 평균 {d.r.mean():+.2f} · 중앙 {d.r.median():+.2f} · "
      f"상위5% 절삭 {d.r[d.r<=d.r.quantile(.95)].mean():+.2f}")
print(f"  상위 1%가 수익의 {d.r.nlargest(max(1,len(d)//100)).sum()/tot*100:.1f}% · "
      f"상위 5%가 {d.r.nlargest(max(1,len(d)//20)).sum()/tot*100:.1f}%")
print("  연도별 초과: " + " ".join(f"{y[2:]}:{v:+.1f}" for y, v in d.groupby(d.date.str[:4]).ex.mean().items()))
n1 = K[(BASEC & (K.fromhi >= -5)).fillna(False)]
a = set(zip(d.ticker, d.date)); b = set(zip(n1.ticker, n1.date))
print(f"\n  [상승장 신고가] 신고가권과 겹침: {len(a & b):,}/{len(a):,}건 ({len(a & b)/max(len(a),1)*100:.1f}%)")
try:
    import verdict; verdict.log_trials("us_bull2nd", 20)
except Exception as e: print(e)
