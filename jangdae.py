# -*- coding: utf-8 -*-
"""장대양봉(매집봉) 실측 — 이 강사 영상에서 **유일하게 안 재본 주장** 하나.

계기: 지식한상 [돈 버는 사람은 '이 5가지'만 봅니다] (성승현 · 2026-09-11 사용자 링크).
영상은 **재탕**이다 — 구체적 방법인 월봉 12평(돌파매수·이탈매도, "이탈 시 80~90% 하락")은
2편에서 66조합으로 전면 기각하고 3편에서 재확인했다([[youtube-swing-reject]]).
나머지는 캔들·패턴·추세·이평선·거래량의 **정의**를 설명하는 초보용 편이다.

안 재본 주장 하나만 잰다:
  "몸통이 긴 **장대양봉**이 많이 보이는 차트가 오를 가능성이 높다 — 매집봉이다.
   장대양봉이 어디에 위치하는지, **저점을 높이면서** 상승하는지 본다."
꼬리(아래꼬리+거래량)·돌파 시 거래량은 이미 쟀고 **둘 다 실측이 정반대**였다.
몸통 크기 자체를 축으로 삼은 적은 없다.

  ① 십분위 — 최근 20일 장대양봉 개수가 많을수록 좋은가
  ② 문턱 × 몸통 크기 정의
  ③ '저점을 높이며' 조건을 얹으면
  ④ 대조군 — 장대**음봉**은 반대인가 (진짜 축이면 부호가 갈려야 한다)

판정: 익일 시가 매수 · 비용차감 · 중복제거 · 같은날 유니버스 대비 초과
     · 학습 2016~22 / 검증 2023~26 / 스트레스 2005~15 · 월블록 CI · 중앙값·절삭평균

    python jangdae.py
"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
from vp_lib import boot_ci

BASE = Path(__file__).parent; TR1, VA0 = "20221231", "20230101"
P = []
for f, mk in (("panel_kp.pkl", "KOSPI"), ("panel_kq.pkl", "KOSDAQ")):
    d = pd.read_pickle(BASE / "data" / f); d["mk"] = mk; P.append(d)
K = pd.concat(P, ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)
K["pref"] = ~K.ticker.str.endswith("0")
K = K[(~K.pref) & (K.close >= 1000) & (K.amt20.fillna(0) >= 3)].copy()
ud = sorted(K.date.unique()); K["di"] = K.date.map({d: i for i, d in enumerate(ud)}).astype(np.int32)
g = K.groupby("ticker", sort=False)
# 몸통 = |종가-시가| ÷ 시가. 양봉이면서 몸통이 큰 날을 '장대양봉' 으로 본다.
K["body"] = (K.close - K.open) / K.open * 100
for th in (3, 5, 7):
    K[f"jd{th}"] = (K.body >= th).astype(np.int8)
    K[f"jdn{th}"] = g[f"jd{th}"].transform(lambda s: s.rolling(20, min_periods=10).sum())
    K[f"um{th}"] = (K.body <= -th).astype(np.int8)          # 장대음봉(대조군)
    K[f"umn{th}"] = g[f"um{th}"].transform(lambda s: s.rolling(20, min_periods=10).sum())
# '저점을 높이며' — 최근 20일 저가 하한이 그 앞 20일보다 높은가
K["lo20"] = g.low.transform(lambda s: s.rolling(20).min())
K["lo20p"] = g.lo20.shift(20)
K["rising"] = (K.lo20 > K.lo20p).fillna(False)
BEN = {h: K.dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in (5, 20, 40)}
NDAY = len([d for d in ud if d >= "20160101"])

def dd(cond, h=20, lo="20160101", hi="20991231"):
    X = K[cond.fillna(False)].dropna(subset=[f"n{h}"]).sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i + h; keep.append(ix)
    d = X.loc[keep].copy(); d = d[(d.date >= lo) & (d.date <= hi)]
    d["r"] = d[f"n{h}"].astype(float); d["ex"] = d.r - d.date.map(BEN[h]); d["ym"] = d.date.str[:6]
    return d[d.r.notna()]
HDR = (f"  {'조건':<30} {'n':>6} {'일':>5} {'승률':>6} {'평균':>7} {'중앙':>7} {'절삭':>7} {'초과':>7} "
       f"{'학습':>7} {'검증':>7} {'스트':>7} {'CI':>7} {'연양수':>6}")
def show(tag, cond, h=20):
    d = dd(cond, h); st = dd(cond, h, lo="20050101", hi="20151231")
    if len(d) < 60: print(f"  {tag:<30} {len(d):>6}  (표본 부족)"); return
    tr = d[d.date <= TR1]; va = d[d.date >= VA0]
    yr = d.groupby(d.date.str[:4]).ex.mean(); trim = d.r[d.r <= d.r.quantile(0.95)].mean()
    print(f"  {tag:<30} {len(d):>6} {len(d)/NDAY:>5.2f} {(d.r>0).mean()*100:>5.1f}% {d.r.mean():>7.2f} "
          f"{d.r.median():>7.2f} {trim:>7.2f} {d.ex.mean():>7.2f} {tr.ex.mean():>7.2f} {va.ex.mean():>7.2f} "
          f"{(st.ex.mean() if len(st)>=60 else np.nan):>7.2f} {boot_ci(d.groupby('ym').ex.mean()):>7.2f} "
          f"{int((yr>0).sum()):>3}/{len(yr)}")

Z = K[K.date >= "20160101"].dropna(subset=["n20", "jdn5"]).copy()
Z["ex"] = Z.n20 - Z.date.map(BEN[20])
print(f"패널 {len(K):,}행 · 판정 대상 {len(Z):,}행")
print("\n" + "=" * 148); print("① 십분위 — 최근 20일 장대양봉 개수 (1=적음 … 10=많음)"); print("=" * 148)
for th in (3, 5, 7):
    v = Z[f"jdn{th}"].astype(float)
    q = pd.qcut(v.rank(method="first"), 10, labels=False)
    m = Z.groupby(q).ex.mean()
    rho = np.corrcoef(np.arange(10), m.reindex(range(10)).values)[0, 1]
    print(f"  몸통 {th}%↑ 개수  " + " ".join(f"{m.get(i,np.nan):>6.2f}" for i in range(10)) + f"   ρ={rho:>+5.2f}")
print("  (참고) 장대음봉 개수")
for th in (3, 5):
    v = Z[f"umn{th}"].astype(float)
    q = pd.qcut(v.rank(method="first"), 10, labels=False)
    m = Z.groupby(q).ex.mean()
    rho = np.corrcoef(np.arange(10), m.reindex(range(10)).values)[0, 1]
    print(f"  몸통 -{th}%↓ 개수 " + " ".join(f"{m.get(i,np.nan):>6.2f}" for i in range(10)) + f"   ρ={rho:>+5.2f}")

print("\n" + "=" * 148); print("② 문턱 (20일 보유)"); print("=" * 148); print(HDR)
for th in (3, 5, 7):
    for n in (2, 3, 5):
        show(f"  몸통 {th}%↑ 가 20일에 {n}회↑", K[f"jdn{th}"] >= n)
    print()
print("=" * 148); print("③ '저점을 높이며' 를 얹으면 · 보유일"); print("=" * 148); print(HDR)
C = (K.jdn5 >= 3)
show("  기준 (몸통5%↑ 3회↑)", C)
show("  + 저점 상승", C & K.rising)
show("  + 저점 하락", C & ~K.rising)
for h in (5, 40):
    show(f"  기준 · {h}일 보유", C, h=h)
print("\n" + "=" * 148); print("④ 대조군 — 장대음봉이 많으면 반대인가"); print("=" * 148); print(HDR)
show("  장대음봉 -5%↓ 3회↑", K.umn5 >= 3)
show("  장대양봉·음봉 둘 다 3회↑", (K.jdn5 >= 3) & (K.umn5 >= 3))
show("  장대양봉만 3회↑·음봉 0회", (K.jdn5 >= 3) & (K.umn5 == 0))
try:
    import verdict; verdict.log_trials("성승현4편_장대양봉", 25)
except Exception as e: print(e)
