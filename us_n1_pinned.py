# -*- coding: utf-8 -*-
"""[상승장 신고가]의 구멍 — 인수합병으로 가격이 묶인 종목(pinned).

2026-09-10 사용자 지적: 오늘 걸린 DoubleVerify(DV)가 "거래량 적고 등폭이 없는 종목" 이다.
확인해 보니 20일 변동성 **0.17%/일** · 최근 20일 고저폭 **1.13%** · 유니버스 하위 3.3% 였다.
8월 8일 거래량 폭증(4천만 주) 뒤 주가가 $13.29~$13.40 에 못 박혀 있다 —
**인수 합의가 난 종목**의 전형이다.

왜 N1 이 이걸 잡는가: 조건이 「52주 고점 -5% 이내 + 조용한 거래량」인데
**딜 픽스된 종목은 그 둘을 완벽하게 만족한다**. 인수가에 붙어 조용히 누워 있으니까.
그런데 기대값은 다르다 — 위로는 인수가에서 막혀 있고 아래로만 열려 있다(딜 무산).

  ① 얼마나 자주 걸리나 — N1 신호 중 '묶인' 종목의 비율
  ② 성적이 실제로 나쁜가 — 묶인 쪽 vs 나머지
  ③ 어디서 잘라야 하나 — 변동성 백분위 문턱
  ④ 빼면 규칙이 좋아지나 (계좌까지)

문턱은 절대값이 아니라 **그날 유니버스 안 백분위**로 잡는다 — 시장 변동성 수준은 해마다 달라진다.

    python us_n1_pinned.py
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
K["a20b"] = g.volume.transform(lambda s: s.shift(3).rolling(20).mean())
K["re_mo"] = K.vm3 / K.a20b * 100
_w = (K.fromhi >= -5).fillna(False)
_sn = (_w.groupby(K.ticker).shift(1).fillna(False).astype(bool)
       .groupby(K.ticker).transform(lambda s: s.rolling(20, min_periods=1).max()).fillna(0) > 0)
N1 = (UNI & UP & _w & ~_sn & (K.re_mo <= 100)).fillna(False)

# '묶임' 측정 두 가지 — 그날 유니버스 안 백분위
BASEU = ((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)
K["volq"] = K[BASEU].groupby("date").vol20.rank(pct=True)      # 20일 변동성 백분위
K["hl20"] = (g.close.transform(lambda s: s.rolling(20).max())
             / g.close.transform(lambda s: s.rolling(20).min()) - 1) * 100   # 20일 고저폭
K["hlq"] = K[BASEU].groupby("date").hl20.rank(pct=True)
BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in (20, 40, 60)}
NDAY = len([d for d in ud if d >= "20160101"])

def dd(cond, h=40, lo="20160101"):
    X = K[cond.fillna(False)].dropna(subset=[f"n{h}"]).sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i: continue
        last[t] = i + h; keep.append(ix)
    d = X.loc[keep].copy(); d = d[d.date >= lo]
    d["r"] = d[f"n{h}"].astype(float); d["ex"] = d.r - d.date.map(BEN[h]); d["ym"] = d.date.str[:6]
    return d[d.r.notna()]

HDR = (f"  {'조건':<30} {'n':>6} {'일':>5} {'승률':>6} {'평균':>7} {'중앙':>7} {'절삭':>7} {'초과':>7} "
       f"{'학습':>7} {'검증':>7} {'학CI':>7} {'검CI':>7} {'연양수':>6}")
def show(tag, cond, h=40):
    d = dd(cond, h)
    if len(d) < 50: print(f"  {tag:<30} {len(d):>6}  (표본 부족)"); return d
    tr = d[d.date <= TR1]; va = d[d.date >= VA0]
    cit = boot_ci(tr.groupby("ym").ex.mean()) if len(tr) >= 25 else np.nan
    civ = boot_ci(va.groupby("ym").ex.mean()) if len(va) >= 25 else np.nan
    yr = d.groupby(d.date.str[:4]).ex.mean(); trim = d.r[d.r <= d.r.quantile(0.95)].mean()
    print(f"  {tag:<30} {len(d):>6} {len(d)/NDAY:>5.2f} {(d.r>0).mean()*100:>5.1f}% {d.r.mean():>7.2f} "
          f"{d.r.median():>7.2f} {trim:>7.2f} {d.ex.mean():>7.2f} {tr.ex.mean():>7.2f} {va.ex.mean():>7.2f} "
          f"{cit:>7.2f} {civ:>7.2f} {int((yr>0).sum()):>3}/{len(yr)}")
    return d

Z = dd(N1)
print(f"[상승장 신고가] 실거래 {len(Z):,}건 (2016~)")
print(f"\n  변동성 백분위 하위 구간이 신호에서 차지하는 비율")
for q in (0.01, 0.03, 0.05, 0.10, 0.20):
    n = int((Z.volq <= q).sum())
    print(f"    하위 {q*100:>4.0f}% : {n:>4}건 ({n/len(Z)*100:>4.1f}%)")

print("\n" + "=" * 150); print("① 묶인 종목 vs 나머지 (40일 보유)"); print("=" * 150); print(HDR)
for q in (0.01, 0.03, 0.05, 0.10):
    show(f"  변동성 하위 {q*100:.0f}% 만", N1 & (K.volq <= q))
print()
for q in (0.01, 0.03, 0.05, 0.10):
    show(f"  변동성 하위 {q*100:.0f}% 제외", N1 & (K.volq > q))
print()
show("원본 (제외 없음)", N1)

print("\n" + "=" * 150); print("② 20일 고저폭으로 잘라도 같은가"); print("=" * 150); print(HDR)
for q in (0.01, 0.03, 0.05):
    show(f"  고저폭 하위 {q*100:.0f}% 만", N1 & (K.hlq <= q))
for q in (0.01, 0.03, 0.05):
    show(f"  고저폭 하위 {q*100:.0f}% 제외", N1 & (K.hlq > q))

print("\n" + "=" * 150); print("③ 묶인 종목은 실제로 어떻게 움직였나 (변동성 하위 3%)"); print("=" * 150)
P = dd(N1 & (K.volq <= 0.03))
if len(P):
    print(f"  {len(P)}건 · 평균 {P.r.mean():+.2f}% · 중앙 {P.r.median():+.2f}% · 승률 {(P.r>0).mean()*100:.1f}%")
    print(f"  분위 5% {np.percentile(P.r,5):+.1f} · 25% {np.percentile(P.r,25):+.1f} · "
          f"75% {np.percentile(P.r,75):+.1f} · 95% {np.percentile(P.r,95):+.1f}")
    print(f"  ±2% 안에서 끝난 비율 {((P.r.abs()<=2).mean()*100):.1f}%  ← 묶여 있으면 여기 몰린다")
    print(f"  -10% 아래로 끝난 비율 {((P.r<=-10).mean()*100):.1f}%  ← 딜 무산 꼬리")
    print("  최근 사례: " + ", ".join(f"{t}({r:+.1f}%)" for t, r in
          zip(P.tail(8).ticker, P.tail(8).r)))
try:
    import verdict; verdict.log_trials("us_n1_pinned", 20)
except Exception as e: print(e)
