# -*- coding: utf-8 -*-
"""자사주 5차 — 화면에 하루 몇 개나 뜨나, 그리고 '사건형' 으로 바꾸면 어떤가.

배선을 마치고 오늘 신호를 세어 보니 **17건**이었다. 백테스트의 '하루 0.56종목' 은
중복제거(보유 중 재진입 금지) 뒤의 숫자고, 이 규칙은 사건이 아니라 **상태**라
같은 종목이 조건을 만족하는 동안 매일 다시 걸린다. [상승장 신고가]에서 하루 436종목이
뜨던 것과 같은 모양이고, 사용자가 그때 "걸리는 건 자체를 줄이라"고 한 부분이다.

  ① 원본(상태형)의 실제 하루 신호 수 — 연도별로
  ② 사건형으로 바꾸면 — '오늘 처음 조건에 들어온 종목' (N1 의 nh5 와 같은 방식)
     ⚠ 조건을 바꾸면 성적도 다시 재야 한다. 이웃까지 확인한다.
  ③ 계좌

    python us_buyback5.py
"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd, FinanceDataReader as fdr
from vp_lib import boot_ci

BASE = Path(__file__).parent; TR1, VA0 = "20221231", "20230101"
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
BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in (20, 40, 60)}
NDAY = len([d for d in ud if d >= "20160101"])

STATE = (UNI & (K.fromhi <= -30) & K.sp60 & (K.ret20 <= -20)).fillna(False)
# 사건형 — 오늘 처음 들어왔다(최근 w거래일은 조건 밖이었다). 종목 자기 이력만으로 정해진다.
def event(state, w=20):
    seen = (state.groupby(K.ticker).shift(1).fillna(False).astype(bool)
            .groupby(K.ticker).transform(lambda s: s.rolling(w, min_periods=1).max()).fillna(0) > 0)
    return (state & ~seen).fillna(False)

print("=" * 96)
print("① 화면에 하루 몇 개나 뜨나 (중복제거 전 · 실제로 보이는 수)")
print("=" * 96)
S16 = K[STATE & (K.date >= "20160101")]
per = S16.groupby("date").size()
print(f"  상태형: 신호 있는 날 {len(per)}일 / 전체 {NDAY}일 · "
      f"하루 평균 {per.sum()/NDAY:.1f}종목 · 중앙 {per.median():.0f} · 최대 {per.max():.0f}")
print("  연도별 하루 평균: " + " ".join(
    f"{y[2:]}:{v:.0f}" for y, v in (S16.groupby(S16.date.str[:4]).size()
                                    / S16.groupby(S16.date.str[:4]).date.nunique()).items()))
for w in (10, 20, 60):
    E = K[event(STATE, w) & (K.date >= "20160101")]
    p2 = E.groupby("date").size()
    print(f"  사건형(최근 {w}일 밖이었다): 하루 평균 {len(E)/NDAY:.2f}종목 · "
          f"신호 있는 날 {len(p2)}일 · 최대 {p2.max() if len(p2) else 0:.0f}")

HDR = (f"  {'조건':<26} {'n':>6} {'일':>5} {'승률':>6} {'평균':>7} {'중앙':>7} {'절삭':>7} {'초과':>7} "
       f"{'학습':>7} {'검증':>7} {'학CI':>7} {'검CI':>7} {'연양수':>6}")
def dd(cond, h=60, lo="20160101", hi="20991231"):
    X = K[cond.fillna(False)].dropna(subset=[f"n{h}"]).sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i: continue
        last[t] = i + h; keep.append(ix)
    d = X.loc[keep].copy(); d = d[(d.date >= lo) & (d.date <= hi)]
    d["r"] = d[f"n{h}"].astype(float); d["ex"] = d.r - d.date.map(BEN[h]); d["ym"] = d.date.str[:6]
    return d[d.r.notna()]
def show(tag, cond, h=60, lo="20160101", hi="20991231"):
    d = dd(cond, h=h, lo=lo, hi=hi)
    if len(d) < 50: print(f"  {tag:<26} {len(d):>6}  (표본 부족)"); return d
    tr = d[d.date <= TR1]; va = d[d.date >= VA0]
    cit = boot_ci(tr.groupby("ym").ex.mean()) if len(tr) >= 25 else np.nan
    civ = boot_ci(va.groupby("ym").ex.mean()) if len(va) >= 25 else np.nan
    yr = d.groupby(d.date.str[:4]).ex.mean(); trim = d.r[d.r <= d.r.quantile(0.95)].mean()
    print(f"  {tag:<26} {len(d):>6} {len(d)/NDAY:>5.2f} {(d.r>0).mean()*100:>5.1f}% {d.r.mean():>7.2f} "
          f"{d.r.median():>7.2f} {trim:>7.2f} {d.ex.mean():>7.2f} {tr.ex.mean():>7.2f} {va.ex.mean():>7.2f} "
          f"{cit:>7.2f} {civ:>7.2f} {int((yr>0).sum()):>3}/{len(yr)}")
    return d

print("\n" + "=" * 148); print("② 사건형으로 바꾸면 성적이 유지되나"); print("=" * 148); print(HDR)
show("상태형 (원본) · 60일", STATE)
for w in (10, 20, 60):
    for h in (40, 60):
        show(f"  사건형 {w}일 · {h}일보유", event(STATE, w), h=h)
    print()
print("  ── 스트레스 2009~15 ──")
show("  상태형 · 60일 · 09~15", STATE, lo="20090101", hi="20151231")
show("  사건형 20일 · 60일 · 09~15", event(STATE, 20), lo="20090101", hi="20151231")
print("\n  ── 복권형 점검 (사건형 20일 · 60일) ──")
d = dd(event(STATE, 20))
if len(d) >= 50:
    tot = d.r.sum()
    print(f"     승률 {(d.r>0).mean()*100:.1f}% · 중앙 {d.r.median():+.2f} · "
          f"절삭 {d.r[d.r<=d.r.quantile(.95)].mean():+.2f} · "
          f"상위1% {d.r.nlargest(max(1,len(d)//100)).sum()/tot*100:.1f}% · "
          f"상위5% {d.r.nlargest(max(1,len(d)//20)).sum()/tot*100:.1f}%")
    print("     연도별 초과: " + " ".join(f"{y[2:]}:{v:+.1f}"
          for y, v in d.groupby(d.date.str[:4]).ex.mean().items()))
