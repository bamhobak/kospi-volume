# -*- coding: utf-8 -*-
"""[조용한 신고가] 검증 CI 하한 -0.5 를 파고든다 — 무엇이 하한을 끌어내리나.

아홉 규칙 중 유일하게 검증(2023~26) 신뢰구간 하한이 음수다(학습 +3.2 / 검증 -0.5).
표본이 32건·13개월로 얇아서인지, 특정 시기·특정 종목이 끌어내리는지 가른다.
  ① 검증구간 거래를 월별로 펼쳐 어느 달이 손실인지
  ② 최악 5건을 빼면 CI 가 어떻게 되나 (꼬리 하나에 흔들리는가)
  ③ 부트스트랩 분포 자체 — 하한이 -0.5 라도 평균이 얼마나 위인가
  ④ 표본을 늘려 본다: 기준2016~ 전체 60건 · 60일 보유로 늘렸을 때
  ⑤ 규칙 조건 중 어느 것이 검증구간에서 약해졌나 (학습 대비 통과율 변화)
"""
import io, os, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, RULES, base = ns["KP"], ns["RULES"], ns["base"]
K, HOLD, STOP, pct, mx, COND = RULES["P1"]
g = K.groupby("ticker", sort=False)
for h in (20, 60):
    if f"n{h}" not in K.columns: K[f"n{h}"] = (g.close.shift(-h)/K.buy-1)*100 - K.cost
def take(cond, hold=HOLD, stop=STOP):
    if stop:
        low = pd.concat([g.low.shift(-i) for i in range(hold)], axis=1).min(axis=1)
        r = np.where((low <= K.buy*(1-stop)).fillna(False), -stop*100-K.cost, K[f"n{hold}"])
    else: r = K[f"n{hold}"].values
    m = cond.fillna(False); X = K[m].copy(); X["_r"] = r[m.values]; X = X.dropna(subset=["_r"])
    di = {x:i for i,x in enumerate(sorted(K.date.unique()))}
    X["di"] = X.date.map(di); X = X.sort_values("di"); keep, last = [], {}
    for t,i,ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t,-10**9) >= i: continue
        last[t] = i+hold; keep.append(ix)
    return X.loc[keep]
def boot(z, n=4000, seed=0):
    if len(z) < 8: return None
    rng = np.random.default_rng(seed); mo = z.date.str[:6].values
    grp = [z._r.values[mo == m] for m in np.unique(mo)]; k = len(grp)
    return np.array([np.concatenate([grp[i] for i in rng.integers(0,k,k)]).mean() for _ in range(n)])
Z = take(COND); V = Z[Z.date >= "20230101"]; T = Z[(Z.date>="20160101")&(Z.date<="20221231")]
print(f"[조용한 신고가] 학습 {len(T)}건 · 검증 {len(V)}건 (40일 보유·손절 -15%)\n")
print("① 검증구간 월별")
for m, gg in V.assign(m=V.date.str[:6]).groupby("m"):
    bar = "".join("+" if x > 0 else "-" for x in gg._r)
    print(f"  {m[:4]}-{m[4:]}  {len(gg):>2}건  평균 {gg._r.mean():>+6.1f}%  최악 {gg._r.min():>+6.1f}%  {bar}")
print("\n② 꼬리 민감도 — 최악 N건을 빼면 (검증)")
b = boot(V); print(f"  전체        {len(V)}건 평균 {V._r.mean():+.2f}% · CI하한 {np.percentile(b,5):+.2f} · 중앙 {np.percentile(b,50):+.2f}")
for n in (1, 2, 3, 5):
    v = V.sort_values("_r").iloc[n:]
    bb = boot(v); print(f"  최악 {n}건 제외 {len(v)}건 평균 {v._r.mean():+.2f}% · CI하한 {np.percentile(bb,5):+.2f} · 중앙 {np.percentile(bb,50):+.2f}")
print("\n③ 부트스트랩 분포 (검증)")
print(f"  5% {np.percentile(b,5):+.1f} · 25% {np.percentile(b,25):+.1f} · 50% {np.percentile(b,50):+.1f}"
      f" · 75% {np.percentile(b,75):+.1f} · 95% {np.percentile(b,95):+.1f} · 음수 확률 {(b<0).mean()*100:.0f}%")
print("\n④ 표본·보유 바꿔 보기")
for nm, z in (("기준 2016~ 전체", Z[Z.date>="20160101"]), ("학습 2016~22", T), ("검증 2023~26", V)):
    bb = boot(z)
    print(f"  {nm:<16}{len(z):>4}건 평균 {z._r.mean():>+6.2f}% 중앙 {z._r.median():>+6.2f} 승률 {(z._r>0).mean()*100:>3.0f}%"
          + (f" CI하한 {np.percentile(bb,5):>+6.2f} 음수확률 {(bb<0).mean()*100:>3.0f}%" if bb is not None else ""))
Z60 = take(COND, 60, STOP); V60 = Z60[Z60.date>="20230101"]; b60 = boot(V60)
print(f"  {'검증·60일 보유':<16}{len(V60):>4}건 평균 {V60._r.mean():>+6.2f}% 중앙 {V60._r.median():>+6.2f} 승률 {(V60._r>0).mean()*100:>3.0f}%"
      + (f" CI하한 {np.percentile(b60,5):>+6.2f}" if b60 is not None else ""))
print("\n⑤ 조건별 통과율 — 학습 대비 검증에서 무엇이 달라졌나 (전 종목-일 기준 %)")
TERMS = {"고점 -10% 이내":K.fromhi>=-10, "신용잔고비<120":K.r16<120, "주간거래대금≤120":K.rw1<=120,
         "외국인5일≥3":K.fw5>=3, "외국인60일≥1":K.fw60>=1, "변동성≤2":K.vol20<=2,
         "업종20일≤0.5":K.sr20<=0.5, "20일등락≤5":K.ret20<=5, "거래대금≥200억":K.amt20>=200}
tr = (K.date>="20160101")&(K.date<="20221231"); va = K.date>="20230101"
print(f"  {'조건':<18}{'학습':>8}{'검증':>8}{'변화':>8}")
for nm, c in TERMS.items():
    a = c[tr].fillna(False).mean()*100; bq = c[va].fillna(False).mean()*100
    print(f"  {nm:<18}{a:>7.1f}%{bq:>7.1f}%{bq-a:>+7.1f}p")
