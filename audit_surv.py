# -*- coding: utf-8 -*-
"""**미국 패널 생존편향 크기 재기** (2026-09-12).

미국 패널은 5,983종목 중 99.7% 가 마지막 달까지 살아 있다 — 21년간 상장폐지가 0건이다.
2005년에 1,839종목, 2026년에 5,677종목으로 **단조 증가**하는 것도 같은 얘기다.
'지금 상장된 종목의 과거' 만 모았기 때문이다. 그때 있다가 사라진 종목이 통째로 빠져 있다.

한국 패널은 폐지 종목이 들어 있다(생존 66.8%). 그래서 **한국을 대리(proxy)로** 쓴다:
한국에서 폐지 종목을 빼면 각 규칙 계열의 성적이 얼마나 부풀려지는지 재고, 그 크기를
미국 규칙의 할인폭으로 삼는다.

  ① 규칙 계열별 — 폐지 포함 vs 폐지 제외 (한국)
  ② 계열별 폐지 비중 — 어떤 신호가 폐지 종목을 많이 집나
  ③ 미국 규칙에 적용할 할인폭 제안

    python audit_surv.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
W = 112


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)


log("kr_scan.pkl 읽는 중")
K = pd.read_pickle(BASE / "data/kr_scan.pkl")
K = K[((K.close >= 1000) & (~K.pref.fillna(False))).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
ud = sorted(K.date.unique()); DI = {d: i for i, d in enumerate(ud)}
K["di"] = K.date.map(DI).astype(np.int32)
UNI = (K.groupby("date").amt20.rank(pct=True) >= 0.6).fillna(False)
JW = K.jw if "jw" in K.columns else pd.Series(False, index=K.index)

# 폐지 종목 = 패널 마지막 달까지 살아남지 못한 종목
END = K.date.max()[:6]
last = K.groupby("ticker").date.max()
DEAD = set(last[last.str[:6] < END].index)
log(f"  {K.ticker.nunique():,}종목 중 폐지 {len(DEAD):,} ({len(DEAD)/K.ticker.nunique()*100:.1f}%)")
K["dead"] = K.ticker.isin(DEAD)

BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in (20, 40, 60)}


def trim(r):
    r = pd.Series(r).dropna()
    return r[r <= r.quantile(0.95)].mean() if len(r) else np.nan


def dd(cond, h, alive_only=False):
    m = cond & UNI & ~JW
    if alive_only: m = m & ~K.dead
    X = K[m.fillna(False)].dropna(subset=[f"n{h}"]).sort_values("di")
    keep, lastd = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if lastd.get(t, -10**9) >= i: continue
        lastd[t] = i + h; keep.append(ix)
    d = X.loc[keep].copy()
    d["r"] = d[f"n{h}"].astype(float); d["ex"] = d.r - d.date.map(BEN[h])
    return d[d.r.notna()]


# 미국 규칙과 같은 계열의 한국 조건들
FAM = [
    ("신고가 계열 (N1 과 같은 축)", 40,
     (K.fromhi >= -5) & (K.ret250 > 0) & (K.vol20 <= 3)),
    ("낙폭과대 (N2·N3 과 같은 축)", 20,
     (K.fromhi <= -30) & (K.ret20 <= -20)),
    ("저PBR 낙폭 (N4 와 같은 축)", 40,
     (K.PBR > 0) & (K.PBR <= 0.8) & (K.ret20 <= -10)),
    ("잔잔한 급등 (N5 와 같은 축)", 60,
     (K.ret250 >= 120) & (K.ret60 > 0) & (K.ret120 > 0)),
    ("전체 유니버스(기준선)", 20, pd.Series(True, index=K.index)),
]

sec("① 폐지 종목을 빼면 성적이 얼마나 부풀려지나 (한국 · 미국 패널의 처지를 흉내)")
print(f"  {'계열':<28}{'보유':>5}{'전체 n':>9}{'생존만 n':>9}{'전체 초과':>10}{'생존만 초과':>12}{'부풀림':>9}"
      f"{'전체 중앙':>10}{'생존만 중앙':>12}")
rows = []
for nm, h, cond in FAM:
    a = dd(cond, h); b = dd(cond, h, alive_only=True)
    if len(a) < 50 or len(b) < 50:
        print(f"  {nm:<28}{h:>4}일  표본 부족"); continue
    infl = b.ex.mean() - a.ex.mean()
    rows.append((nm, h, infl))
    print(f"  {nm:<28}{h:>4}일{len(a):>9,}{len(b):>9,}{a.ex.mean():>10.2f}{b.ex.mean():>12.2f}"
          f"{infl:>+9.2f}{a.r.median():>10.2f}{b.r.median():>12.2f}")

sec("② 계열별 폐지 종목 비중 — 어떤 신호가 나중에 사라질 종목을 많이 집나")
for nm, h, cond in FAM:
    d = dd(cond, h)
    if len(d) < 50: continue
    print(f"  {nm:<28} 신호 {len(d):>7,}건 중 폐지 종목 {int(d.dead.sum()):>6,}건 ({d.dead.mean()*100:>5.1f}%)"
          f" · 폐지분 평균수익 {d[d.dead].r.mean():>7.2f}% vs 생존분 {d[~d.dead].r.mean():>6.2f}%")

sec("③ 미국 규칙에 적용할 할인폭")
if rows:
    print("  한국에서 잰 부풀림(생존만 - 전체)을 그대로 미국 규칙의 초과수익에서 뺀다.")
    print("  ⚠ 하한이다 — 미국은 파산·인수 비중이 한국과 다르고, 한국 패널도 2005~2017 백필의")
    print("     폐지 커버리지가 완전하지 않다.")
    for nm, h, infl in rows:
        print(f"     {nm:<28} {h:>2}일 · 할인 {infl:+.2f}%p")
log("끝")
