# -*- coding: utf-8 -*-
"""[저PBR 낙폭] PBR≤0.8 로 바꾼 뒤 사이트 stats 블록에 넣을 숫자를 새로 뽑는다.

사이트가 보여주는 숫자는 전부 **2016년 이후** 기준이고(학습 2016~22 / 검증 2023~26),
월 신호 건수는 '신호가 난 달' 분포로 적는다. 여기서 뽑은 값을 index.html 의
stats 에 그대로 옮긴다 — 손으로 고쳐 쓰면 문턱과 숫자가 어긋난다.
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import verdict

BASE = Path(__file__).parent
src = (BASE / "portfolio.py").read_text(encoding="utf-8")
ns = {"__file__": str(BASE / "portfolio.py")}
real = sys.stdout
sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES = ns["KP"], ns["KQ"], ns["RULES"]
K, hold, stop, pct, mx, cond = RULES["D2"]

m = cond.fillna(False)
X = K[m].dropna(subset=[f"n{hold}"]).copy()
di = {d: i for i, d in enumerate(sorted(K.date.unique()))}
X["di"] = X.date.map(di)
X = X.sort_values("di")
keep, last = [], {}
for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
    if last.get(t, -10 ** 9) >= i:
        continue
    last[t] = i + hold
    keep.append(ix)
X = X.loc[keep]
X["r"] = X[f"n{hold}"]
X["y"] = X.date.str[:4]
X["mm"] = X.date.str[:6]

def blk(z, nm):
    if not len(z):
        print(f"  {nm}: 0건"); return
    pf = z[z.r > 0].r.sum() / abs(z[z.r < 0].r.sum()) if (z.r < 0).any() else float("inf")
    ci = verdict.boot_ci(z.groupby("mm").r.mean(), 0.10)
    print(f"  {nm:<18}{len(z):>4}건 평균 {z.r.mean():+.2f}% 중앙 {z.r.median():+.2f}% "
          f"승률 {(z.r > 0).mean() * 100:.0f}% PF {pf:.2f} 최악 {z.r.min():+.1f}% 월CI하한 {ci:+.1f}%")

print("[저PBR 낙폭] PBR≤0.8 · 40일 보유 · 손절 없음")
blk(X[(X.date >= "20160101")], "기준 2016~26")
blk(X[(X.date >= "20160101") & (X.date <= "20221231")], "학습 2016~22")
blk(X[X.date >= "20230101"], "검증 2023~26")
blk(X[X.date < "20160101"], "스트레스 2005~15")

V = X[X.date >= "20230101"]
print("\n검증구간 연도별")
for y, g in V.groupby("y"):
    print(f"  {y}  {len(g):>2}건 평균 {g.r.mean():+.2f}% 중앙 {g.r.median():+.2f}% 승률 {(g.r > 0).mean() * 100:.0f}%")

print("\n월 분포 (검증구간 2023~26)")
d0, d1 = "202301", sorted(K.date.unique())[-1][:6]
span = (int(d1[:4]) - int(d0[:4])) * 12 + int(d1[4:6]) - int(d0[4:6]) + 1
cnt = V.groupby("mm").size()
print(f"  전체 {span}개월 중 신호 난 달 {len(cnt)}개 · 난 달 기준 중앙 {int(cnt.median())}건 · "
      f"가장 많았던 달 {cnt.idxmax()} {cnt.max()}건 · 월평균 {len(V) / span:.1f}건")
