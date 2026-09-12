# -*- coding: utf-8 -*-
"""생존편향 재측정 — 사이트 설명과 내 1차 측정이 **반대로** 나와 원인을 가린다 (2026-09-12).

  사이트: "낙폭 규칙이 잡는 폐지 종목은 인수·합병이라 +10~14%, 빼면 과소평가"
  1차:    "낙폭 계열 폐지분 -1.48% vs 생존분 +1.69% → 빼면 과대평가"

가능한 원인 넷을 하나씩 갈라 본다.
  ① **조건 정의** — 1차는 느슨했다(fromhi≤-30 & ret20≤-20). 규칙은 훨씬 좁다(su1·업종·srd 등).
  ② **패널 수리** — 1차는 오늘 수리한 패널, 사이트는 수리 전 패널에서 잰 값이다.
  ③ **점프 창(jw) 제외** — 1차는 뺐고 예전엔 없던 개념이다.
  ④ **'폐지' 정의** — 마지막 거래일 기준. 정리매매까지 담겼나 vs 거래정지로 끊겼나.

각 계열을 ① 느슨한 정의 ② 규칙에 가까운 정의 로 나누고, jw 포함/제외를 교차해 본다.

    python audit_surv2.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
W = 118


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)


log("kr_scan.pkl 읽는 중")
K = pd.read_pickle(BASE / "data/kr_scan.pkl")
K = K[((K.close >= 1000) & (~K.pref.fillna(False))).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
ud = sorted(K.date.unique()); DI = {d: i for i, d in enumerate(ud)}
K["di"] = K.date.map(DI).astype(np.int32)
UNI = (K.groupby("date").amt20.rank(pct=True) >= 0.6).fillna(False)
JW = (K.jw if "jw" in K.columns else pd.Series(False, index=K.index)).fillna(False)

END = K.date.max()[:6]
last = K.groupby("ticker").date.max()
DEAD = set(last[last.str[:6] < END].index)
K["dead"] = K.ticker.isin(DEAD)
log(f"  {K.ticker.nunique():,}종목 · 폐지 {len(DEAD):,} ({len(DEAD)/K.ticker.nunique()*100:.1f}%)")

BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in (20, 40, 60)}


def dd(cond, h, use_jw=True, alive_only=False):
    m = cond & UNI
    if use_jw: m = m & ~JW
    if alive_only: m = m & ~K.dead
    X = K[m.fillna(False)].dropna(subset=[f"n{h}"]).sort_values("di")
    keep, lastd = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if lastd.get(t, -10**9) >= i: continue
        lastd[t] = i + h; keep.append(ix)
    d = X.loc[keep].copy()
    d["r"] = d[f"n{h}"].astype(float); d["ex"] = d.r - d.date.map(BEN[h])
    return d[d.r.notna()]


# 국면 게이트(코스피 60일선 아래) — 규칙에 가까운 정의에 쓴다
IX = K.groupby("date").close.median()
IXMA = IX.rolling(60).mean()
DN60 = K.date.map((IX < IXMA)).fillna(False)

FAM = [
    # (이름, 보유, 느슨한 정의, 규칙에 가까운 정의)
    ("낙폭과대 (N2·N3)", 20,
     (K.fromhi <= -30) & (K.ret20 <= -20),
     DN60 & (K.ret20 <= -30) & (K.su1 >= 2) & (K.amt20.fillna(0) >= 10)),
    ("저PBR 낙폭 (N4)", 40,
     (K.PBR > 0) & (K.PBR <= 0.8) & (K.ret20 <= -10),
     DN60 & (K.PBR > 0) & (K.PBR <= 0.8) & (K.ret20 <= -10) & (K.su1 >= 2) & (K.amt20.fillna(0) >= 5)),
    ("신고가 (N1)", 40,
     (K.fromhi >= -5) & (K.ret250 > 0) & (K.vol20 <= 3),
     (K.fromhi >= -5) & (K.ret250 > 0) & (K.vol20 <= 3) & (K.rw1 <= 100) & (K.amt20.fillna(0) >= 10)),
    ("잔잔한 급등 (N5)", 60,
     (K.ret250 >= 120) & (K.ret60 > 0) & (K.ret120 > 0),
     (K.ret250 >= 120) & (K.ret60 > 0) & (K.ret120 > 0) & (K.vol20 <= 1.5) & (K.amt20.fillna(0) >= 10)),
]

sec("① 조건 정의가 원인인가 — 느슨한 정의 vs 규칙에 가까운 정의")
print(f"  {'계열':<20}{'정의':<8}{'신호':>8}{'폐지비중':>9}{'폐지분 수익':>12}{'생존분 수익':>12}{'차이':>9}")
for nm, h, loose, tight in FAM:
    for lbl, c in (("느슨", loose), ("규칙형", tight)):
        d = dd(c, h)
        if len(d) < 80:
            print(f"  {nm if lbl=='느슨' else '':<20}{lbl:<8}{len(d):>8}  (부족)"); continue
        dr = d[d.dead].r; al = d[~d.dead].r
        if len(dr) < 20:
            print(f"  {nm if lbl=='느슨' else '':<20}{lbl:<8}{len(d):>8,}{d.dead.mean()*100:>8.1f}%  (폐지 표본 부족)"); continue
        print(f"  {nm if lbl=='느슨' else '':<20}{lbl:<8}{len(d):>8,}{d.dead.mean()*100:>8.1f}%"
              f"{dr.mean():>12.2f}{al.mean():>12.2f}{dr.mean()-al.mean():>+9.2f}")
    print()

sec("② 점프 창(jw) 제외가 원인인가")
print(f"  {'계열':<20}{'jw':<8}{'신호':>8}{'폐지비중':>9}{'폐지분':>10}{'생존분':>10}{'차이':>9}")
for nm, h, loose, tight in FAM[:2]:
    for lbl, uj in (("제외", True), ("포함", False)):
        d = dd(tight, h, use_jw=uj)
        if len(d) < 80 or d.dead.sum() < 20:
            print(f"  {nm if lbl=='제외' else '':<20}{lbl:<8}{len(d):>8}  (부족)"); continue
        dr = d[d.dead].r; al = d[~d.dead].r
        print(f"  {nm if lbl=='제외' else '':<20}{lbl:<8}{len(d):>8,}{d.dead.mean()*100:>8.1f}%"
              f"{dr.mean():>10.2f}{al.mean():>10.2f}{dr.mean()-al.mean():>+9.2f}")
    print()

sec("③ 폐지 종목이 어떻게 끝났나 — 인수합병인가 파산인가")
print("  마지막 60거래일 수익률로 가른다. 정리매매를 거치면 크게 빠지고, 인수되면 안 빠진다.")
g = K.groupby("ticker", sort=False)
lastrow = K.groupby("ticker").tail(1).set_index("ticker")
first = K.groupby("ticker").head(1).set_index("ticker")
dd_list = sorted(DEAD)
tail60 = {}
for t in dd_list:
    sub = K.loc[K.ticker == t, "close"].values
    if len(sub) >= 61: tail60[t] = sub[-1] / sub[-61] - 1
tl = pd.Series(tail60) * 100
print(f"  폐지 {len(DEAD):,}종목 중 마지막 60일 수익 계산 가능 {len(tl):,}")
print(f"     중앙 {tl.median():+.1f}% · 평균 {tl.mean():+.1f}%")
for lo, hi, nm in ((-1e9, -50, "-50% 이하 (정리매매·파산형)"), (-50, -20, "-50~-20%"),
                   (-20, 20, "-20~+20% (인수·합병형)"), (20, 1e9, "+20% 이상")):
    m = (tl > lo) & (tl <= hi)
    print(f"     {nm:<26} {int(m.sum()):>5,}종목 ({m.mean()*100:>4.1f}%)")

sec("④ 결론 — 미국 규칙에 적용할 순 편향")
print("  순 편향 = (생존만 초과) - (전체 초과) - (유니버스 부풀림)")
u_all = dd(pd.Series(True, index=K.index), 20)
u_alv = dd(pd.Series(True, index=K.index), 20, alive_only=True)
ubias = u_alv.ex.mean() - u_all.ex.mean()
print(f"  유니버스 부풀림 {ubias:+.2f}%p\n")
print(f"  {'계열':<20}{'정의':<8}{'전체 초과':>10}{'생존만 초과':>12}{'순 편향':>10}")
for nm, h, loose, tight in FAM:
    for lbl, c in (("느슨", loose), ("규칙형", tight)):
        a = dd(c, h); b = dd(c, h, alive_only=True)
        if len(a) < 80 or len(b) < 80: continue
        print(f"  {nm if lbl=='느슨' else '':<20}{lbl:<8}{a.ex.mean():>10.2f}{b.ex.mean():>12.2f}"
              f"{b.ex.mean()-a.ex.mean()-ubias:>+10.2f}")
    print()
log("끝")
