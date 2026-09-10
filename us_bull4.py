# -*- coding: utf-8 -*-
"""상승장 2호 후보 — 기준선을 같은 부분집합으로 맞추고 문턱·조합을 본다.

정찰(us_bull3.py)에서 살아난 비가격 축 넷:
  EPS 수준(흑자)  ρ+0.99 · 자사주 집행/시총 ρ+0.94 · EPS 1년 성장 ρ+0.88 · PBR(낮을수록) ρ-0.86
  (내부자 순매수는 상승장에서 **역방향**(ρ-0.80)이라 접는다)

⚠ **기준선 함정**: 이 축들은 SEC 재무가 있는 종목에만 있다(결측 46~88%). 재무가 있는 종목은
   원래 크고 커버리지가 좋다. 전체 유니버스와 견주면 그 성질이 신호의 공으로 둔갑한다 —
   [[backtest-pitfalls]] 네 번째 함정이 실적·애널리스트 축을 죽인 게 정확히 이 방식이었다.
   그래서 **두 기준선을 나란히** 낸다:
     초과(전체)  = 그날 유니버스 전체 평균 대비   ← 부풀려진 값
     초과(같은집합) = 그날 **같은 재무 항목이 있는 종목들** 평균 대비   ← 이게 진짜다
   둘이 크게 벌어지면 그 축은 '재무가 있는 종목이 원래 좋다' 를 보고 있는 것이다.

    python us_bull4.py
"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd, FinanceDataReader as fdr
from vp_lib import boot_ci

BASE = Path(__file__).parent; TR1, VA0 = "20221231", "20230101"
src = open(BASE / "us_bull3.py", encoding="utf-8").read()
exec(src.split('BEN = {h:')[0].split('"""', 2)[2])       # 재료 준비까지만 빌려 쓴다

NDAY = len([d for d in ud if d >= "20160101"])
BASEC = (UNI & UP).fillna(False)
HAS_EPS = BASEC & K.eps_.notna()
HAS_PBR = BASEC & K.PBR.notna() & (K.PBR > 0)
HAS_BB = BASEC & K.sp60
BENS = {}
for h in (20, 40, 60):
    BENS[("all", h)] = K[BASEC].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean()
    BENS[("eps", h)] = K[HAS_EPS].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean()
    BENS[("pbr", h)] = K[HAS_PBR].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean()
    BENS[("bb", h)] = K[HAS_BB].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean()
print(f"상승 국면 유니버스 하루 평균 {int(BASEC.sum())/NDAY:,.0f}종목 · "
      f"EPS 있는 종목 {int(HAS_EPS.sum())/NDAY:,.0f} · PBR {int(HAS_PBR.sum())/NDAY:,.0f} · "
      f"자사주집행 {int(HAS_BB.sum())/NDAY:,.0f}")

def dd(cond, h):
    X = K[cond.fillna(False)].dropna(subset=[f"n{h}"]).sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i: continue
        last[t] = i + h; keep.append(ix)
    d = X.loc[keep].copy(); d = d[d.date >= "20160101"]
    d["r"] = d[f"n{h}"].astype(float); d["ym"] = d.date.str[:6]
    return d[d.r.notna()]

HDR = (f"  {'조건':<30} {'n':>6} {'일':>5} {'승률':>6} {'중앙':>7} {'절삭':>7} "
       f"{'초과(전체)':>10} {'초과(같은집합)':>13} {'학습':>7} {'검증':>7} {'학CI':>7} {'검CI':>7} {'연양수':>6}")
def show(tag, cond, h=40, ben="eps"):
    d = dd(cond, h)
    if len(d) < 60: print(f"  {tag:<30} {len(d):>6}  (표본 부족)"); return
    d["exA"] = d.r - d.date.map(BENS[("all", h)])
    d["ex"] = d.r - d.date.map(BENS[(ben, h)])
    tr = d[d.date <= TR1]; va = d[d.date >= VA0]
    cit = boot_ci(tr.groupby("ym").ex.mean()) if len(tr) >= 25 else np.nan
    civ = boot_ci(va.groupby("ym").ex.mean()) if len(va) >= 25 else np.nan
    yr = d.groupby(d.date.str[:4]).ex.mean(); trim = d.r[d.r <= d.r.quantile(0.95)].mean()
    print(f"  {tag:<30} {len(d):>6} {len(d)/NDAY:>5.1f} {(d.r>0).mean()*100:>5.1f}% {d.r.median():>7.2f} "
          f"{trim:>7.2f} {d.exA.mean():>10.2f} {d.ex.mean():>13.2f} {tr.ex.mean():>7.2f} {va.ex.mean():>7.2f} "
          f"{cit:>7.2f} {civ:>7.2f} {int((yr>0).sum()):>3}/{len(yr)}")

K["pbr_q"] = K[HAS_PBR].groupby("date").PBR.rank(pct=True)
K["bb_q"] = K[HAS_BB].groupby("date").bbcap.rank(pct=True)
K["eps_q"] = K[HAS_EPS].groupby("date").eps_.rank(pct=True)

print("\n" + "=" * 156); print("① 축 하나씩 (40일 보유)"); print("=" * 156); print(HDR)
show("흑자 (EPS>0)", BASEC & (K.eps_ > 0), ben="eps")
show("EPS 상위 50%", BASEC & (K.eps_q >= 0.5), ben="eps")
show("EPS 상위 30%", BASEC & (K.eps_q >= 0.7), ben="eps")
print()
show("PBR 하위 30% (싼 쪽)", BASEC & (K.pbr_q <= 0.3), ben="pbr")
show("PBR 하위 20%", BASEC & (K.pbr_q <= 0.2), ben="pbr")
show("PBR ≤ 1.5", BASEC & (K.PBR > 0) & (K.PBR <= 1.5), ben="pbr")
print()
show("자사주 집행 상위 30%", BASEC & (K.bb_q >= 0.7), ben="bb")
show("자사주 집행 상위 20%", BASEC & (K.bb_q >= 0.8), ben="bb")
show("자사주/시총 ≥ 1%", BASEC & (K.bbcap >= 1), ben="bb")
print()
show("EPS 성장 상위 30%", BASEC & (K.deps >= K.deps.quantile(0.7)), ben="eps")

print("\n" + "=" * 156); print("② 둘씩 묶으면"); print("=" * 156); print(HDR)
show("흑자 & PBR 하위 30%", BASEC & (K.eps_ > 0) & (K.pbr_q <= 0.3), ben="pbr")
show("흑자 & 자사주 상위 30%", BASEC & (K.eps_ > 0) & (K.bb_q >= 0.7), ben="bb")
show("PBR 하위 30% & 자사주 상위 30%", BASEC & (K.pbr_q <= 0.3) & (K.bb_q >= 0.7), ben="bb")
show("흑자 & EPS성장 상위 30%", BASEC & (K.eps_ > 0) & (K.deps >= K.deps.quantile(0.7)), ben="eps")
print()
print("  ── 셋 ──")
show("흑자 & 저PBR30 & 자사주30", BASEC & (K.eps_ > 0) & (K.pbr_q <= 0.3) & (K.bb_q >= 0.7), ben="bb")
show("흑자 & 저PBR30 & 자사주/시총1%", BASEC & (K.eps_ > 0) & (K.pbr_q <= 0.3) & (K.bbcap >= 1), ben="bb")

print("\n" + "=" * 156); print("③ 살아남은 것의 보유일"); print("=" * 156); print(HDR)
for h in (20, 40, 60):
    show(f"흑자 & 저PBR30 & 자사주30 · {h}일",
         BASEC & (K.eps_ > 0) & (K.pbr_q <= 0.3) & (K.bb_q >= 0.7), h=h, ben="bb")
print()
print("  [상승장 신고가]와 겹침")
n1 = set(zip(K[(UNI & UP & (K.fromhi >= -5)).fillna(False)].ticker,
             K[(UNI & UP & (K.fromhi >= -5)).fillna(False)].date))
c = BASEC & (K.eps_ > 0) & (K.pbr_q <= 0.3) & (K.bb_q >= 0.7)
a = set(zip(K[c.fillna(False)].ticker, K[c.fillna(False)].date))
print(f"    후보 {len(a):,}건 · 신고가권 {len(n1):,}건 · 겹침 {len(a & n1):,}건 "
      f"({len(a & n1)/max(len(a),1)*100:.1f}%)")
try:
    import verdict; verdict.log_trials("us_bull2nd", 25)
except Exception as e: print(e)
