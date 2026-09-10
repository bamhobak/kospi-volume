# -*- coding: utf-8 -*-
"""왜 다중검정에서 기각됐나 — 문턱을 분해해서 본다.

[잔잔한 급등주] 는 규칙·계좌 증거가 좋은데 verdict.judge 에서 기각됐다.
'기각' 만 전하면 판단을 못 하므로 **무엇이 얼마나 모자랐는지** 를 분해한다.

  ① 본페로니 — 필요한 t값과 실제 t값
  ② Deflated Sharpe — '우연히 나올 최대 샤프' sr0 는 시험수 N 과 표본길이 T 로만 정해진다
  ③ 그럼 얼마나 있어야 통과하나 — 필요한 T(개월), 필요한 N
  ④ N 을 몇으로 세는 게 옳은가 — 겹치는 셀을 따로 세면 과잉 처벌이다
  ⑤ 구간을 2005~ 로 늘리면 (월 수가 두 배가 된다)

    python us_tech7.py
"""
import sys, math, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats as st
import verdict
from vp_lib import boot_ci

BASE = Path(__file__).parent
K = pd.read_pickle(BASE / "data/us_scan.pkl")
K = K[((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
ud = sorted(K.date.unique()); K["di"] = K.date.map({d: i for i, d in enumerate(ud)}).astype(np.int32)
UNI = (K.groupby("date").amt20.rank(pct=True) >= 0.6).fillna(False)
TK = K.ticker
K["r1"] = K.groupby(TK, sort=False).close.pct_change() * 100
K["absr"] = K.groupby(TK, sort=False).r1.transform(lambda s: s.abs().rolling(60).mean())
K["multi"] = (K.ret60 > 0) & (K.ret120 > 0) & (K.ret250 > 0)
BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in (40, 60)}

def dd(cond, h, lo):
    X = K[(cond & UNI).fillna(False)].dropna(subset=[f"n{h}"])
    X = X[X.date >= lo].sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i + h; keep.append(ix)
    d = X.loc[keep].copy()
    d["r"] = d[f"n{h}"].astype(float); d["ex"] = d.r - d.date.map(BEN[h]); d["ym"] = d.date.str[:6]
    return d[d.r.notna()]

def cond(rt): return K.multi & (K.ret250 >= rt) & (K.absr <= 1.5)

W = 104
CASES = [("1년 120%↑ · 40일 · 2016~", cond(120), 40, "20160101"),
         ("1년 150%↑ · 40일 · 2016~", cond(150), 40, "20160101"),
         ("1년 120%↑ · 60일 · 2016~", cond(120), 60, "20160101"),
         ("1년 120%↑ · 40일 · 2005~", cond(120), 40, "20050101"),
         ("1년 150%↑ · 40일 · 2005~", cond(150), 40, "20050101"),
         ("1년 120%↑ · 60일 · 2005~", cond(120), 60, "20050101")]
M = {}
for nm, c, h, lo in CASES:
    d = dd(c, h, lo); M[nm] = d.groupby("ym").ex.mean().dropna()

print("\n" + "=" * W)
print("① 본페로니 — 필요한 t값 vs 실제 t값")
print("=" * W)
print("  유의수준 10% 를 시험수 N 으로 나눈다. N=161 이면 alpha = 0.10/161 = 0.000621,")
print("  즉 **99.938% 하한**을 보라는 뜻이다. 정규분포로 옮기면 t > 3.23 을 요구한다.")
print()
print(f"  {'경우':<26}{'월수':>5}{'월평균':>8}{'표준편차':>9}{'표준오차':>9}{'실제 t':>8}{'필요 t':>8}{'판정':>6}")
N = 161
need_t = st.norm.ppf(1 - 0.10 / N)
for nm in M:
    r = M[nm]; T = len(r); se = r.std(ddof=1) / math.sqrt(T); t = r.mean() / se
    print(f"  {nm:<26}{T:>5}{r.mean():>8.2f}{r.std(ddof=1):>9.2f}{se:>9.2f}{t:>8.2f}{need_t:>8.2f}"
          f"{'통과' if t >= need_t else '미달':>6}")
print(f"  → 보정 전(90% · t 1.28) 은 넘는데 보정 후(t {need_t:.2f}) 는 못 넘는다.")
print("    부족한 건 '수익이 작아서' 가 아니라 **표준오차가 커서** 다. 월 변동이 8~13% 인데")
print("    월 수가 64~107 개뿐이라 평균의 오차가 크다.")

print("\n" + "=" * W)
print("② Deflated Sharpe — '우연히 나올 최대 샤프' 가 얼마인가")
print("=" * W)
print("  sr0 = sqrt(1/(T-1)) × [(1-γ)·Z(1-1/N) + γ·Z(1-1/(N·e))]   (López de Prado)")
print("  **N 과 T 만으로 정해진다.** 실력과 무관하다 — N 개를 훑으면 그중 최고는 이만큼 나온다.")
print()
print(f"  {'경우':<26}{'월수 T':>7}{'샤프':>8}{'우연 최대 sr0':>14}{'차이':>8}{'DSR':>8}{'필요':>7}")
for nm in M:
    r = M[nm]; d = verdict.deflated_sharpe(r, N)
    print(f"  {nm:<26}{d['T']:>7}{d['sr']:>8.3f}{d['sr0']:>14.3f}{d['sr']-d['sr0']:>8.3f}"
          f"{d['dsr']*100:>7.1f}%{'95%':>7}")
print("  → 샤프가 sr0 보다 **작으면** 애초에 '우연보다 못하다' 는 뜻이라 DSR 이 50% 아래로 간다.")

print("\n" + "=" * W)
print("③ 그럼 얼마나 있어야 통과하나 (1년 150%↑ · 40일 · 2016~ 기준)")
print("=" * W)
r = M["1년 150%↑ · 40일 · 2016~"]; d0 = verdict.deflated_sharpe(r, N)
sr, sk, ku = d0["sr"], d0["skew"], d0["kurt"]
den = math.sqrt(max(1 - sk * sr + (ku - 1) / 4 * sr ** 2, 1e-9))
need = None
for T in range(len(r), 3000):
    sr0 = verdict.expected_max_sharpe(N, 1.0 / (T - 1))
    if (sr - sr0) * math.sqrt(T - 1) / den >= st.norm.ppf(0.95): need = T; break
print(f"  지금 샤프 {sr:.3f} 를 그대로 유지한다고 치면,")
print(f"  DSR 95% 를 넘으려면 월 **{need}개** 가 필요하다 (지금 {len(r)}개 · 약 {need/12:.0f}년치).")
print(f"  본페로니 t {need_t:.2f} 를 넘으려면 표준오차가 지금의 {r.mean()/need_t/ (r.std(ddof=1)/math.sqrt(len(r))):.2f} 배가 돼야 하고,")
tt = (r.std(ddof=1) * need_t / r.mean()) ** 2
print(f"  표준편차가 그대로라면 월 **{tt:.0f}개** 가 필요하다 (약 {tt/12:.0f}년치).")
print("  → 즉 '더 좋아져야' 가 아니라 **'더 오래 봐야'** 통과한다.")
print("    ⚠ 그리고 그 '더 오래' 는 이미 갖고 있었다 — 처음 판정을 2016~ 40일 보유로만 돌린 게")
print("      실수였다. 계좌가 고른 건 **60일 보유**고 패널은 2005 부터 있다. 아래 ⑤ 를 보라.")

print("\n" + "=" * W)
print("④ N 을 161 로 세는 게 옳은가 — 겹치는 셀을 따로 세면 과잉 처벌이다")
print("=" * W)
print("  본페로니는 **서로 독립인 시험**을 가정한다. 그런데 우리 30칸은")
print("  (150%↑ ⊂ 120%↑ ⊂ 80%↑) 처럼 **포개진 부분집합**이고 같은 데이터를 쓴다.")
print("  독립 시험 30개가 아니라 사실상 '문턱 하나를 흔든 것' 에 가깝다.")
print()
print(f"  {'N':>6}{'필요 t':>9}{'150↑ 보정CI':>13}{'150↑ DSR':>11}{'120↑ 보정CI':>13}{'120↑ DSR':>11}")
r150 = M["1년 150%↑ · 40일 · 2016~"]; r120 = M["1년 120%↑ · 40일 · 2016~"]
for n in (1, 10, 20, 40, 161, 1000, 16159):
    a = min(0.10 / n, 0.10)
    d1 = verdict.deflated_sharpe(r150, max(n, 2)); d2 = verdict.deflated_sharpe(r120, max(n, 2))
    print(f"  {n:>6}{st.norm.ppf(1-a):>9.2f}{boot_ci(r150, a):>13.2f}{d1['dsr']*100:>10.1f}%"
          f"{boot_ci(r120, a):>13.2f}{d2['dsr']*100:>10.1f}%")
print("  → N 을 아무리 낮춰 잡아도(N=1, 보정 없음) DSR 이 150↑ 조차 95% 에 못 미친다면")
print("    시험수 탓이 아니라 **표본 자체가 얇은 것**이다. 위 표에서 확인하라.")

print("\n" + "=" * W)
print("⑤ 참고 — 보정을 걷어낸 원래 성적")
print("=" * W)
print(f"  {'경우':<26}{'월수':>6}{'월평균':>9}{'90% 하한':>11}{'연환산 샤프':>12}")
for nm in M:
    r = M[nm]
    print(f"  {nm:<26}{len(r):>6}{r.mean():>9.2f}{boot_ci(r, 0.10):>11.2f}"
          f"{r.mean()/r.std(ddof=1)*math.sqrt(12):>12.2f}")
