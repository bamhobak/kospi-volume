# -*- coding: utf-8 -*-
"""**지수 제외 3차 — 생존편향 감사** (2026-09-15).

2차에서 6칸이 통과했다. 가장 센 것은 **'지수 제외 + 고점대비 -50% 이하'** 다
(20일 중앙 +4.14% · 초과 +5.77%p). 그런데 이 조합은 **폐지 직전 종목과 겹치는 자리**다.

⚠ 결정적 의심: 수익률 컬럼 n10·n20 은 **앞으로 h거래일 뒤가 있어야** 값이 생긴다.
   지수에서 빠진 직후 상장폐지·거래정지된 종목은 그 값이 **결측**이고, dropna 로
   조용히 표본에서 빠진다. 즉 '제외 뒤 살아남은 것만' 세었을 수 있다.
   이건 이 프로젝트가 반복해서 당한 부류다 — 터지지 않고 좋은 쪽으로 틀린다.

여기서 재는 것
  ① 이벤트 중 수익률이 **결측인 비율** — 이게 크면 2차 결과는 못 쓴다
  ② 결측을 보수적으로 메워 다시 계산 — -50% / -100% 두 가정
  ③ 결측 종목이 실제로 뭐였나 (마지막 거래일·주가)
  ④ 유니버스 조건이 이미 걸러 주는가 (주가 1,000원·거래대금 10억)

    python newrule_index3.py
"""
import sqlite3, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from vp_lib import BASE, log

A = pd.read_pickle(BASE / "data/vp_kr.pkl")
uni = ((~A.pref) & (A.close >= 1000) & (A.amt20.fillna(0) >= 10) & (~A.dil.fillna(False))).fillna(False)
A["_uni"] = uni
log(f"패널 {len(A):,}행")

con = sqlite3.connect(BASE / "data/index_members.db")
M = pd.read_sql("SELECT idx,date,ticker FROM members", con)
M["ticker"] = M.ticker.astype(str).str.zfill(6)
cal = np.array(sorted(A.date.unique()))


def onday(s):
    i = np.searchsorted(cal, s, "left")
    return cal[i] if i < len(cal) else None


EV = []
for ix, g in M.groupby("idx"):
    ds = sorted(g.date.unique())
    mem = {d: set(g[g.date == d].ticker) for d in ds}
    for a, b in zip(ds, ds[1:]):
        d = onday(b)
        if d is None: continue
        for t in mem[a] - mem[b]: EV.append((ix, t, d))
E = pd.DataFrame(EV, columns=["idx", "ticker", "date"]).drop_duplicates(["ticker", "date"])
log(f"제외 이벤트 {len(E):,}건 (종목·날짜 중복 제거)")

# 패널에 붙인다 — 유니버스 밖이면 애초에 후보가 아니다
A["_k"] = A.ticker + A.date
K = set(E.ticker + E.date)
X = A[A._k.isin(K)].copy()
log(f"패널에서 찾은 행 {len(X):,} · 그중 유니버스 통과 {int(X._uni.sum()):,}")
X = X[X._uni]
X["yr"] = X.date.str[:4]
X["last"] = X.ticker.map(A.groupby("ticker").date.max())   # 그 종목의 패널 마지막 거래일

print("\n" + "=" * 112)
print("① 제외 이벤트 중 수익률이 결측인 비율 — 결측 = 그 뒤 거래가 끊긴 것")
print("=" * 112)
print(f"  {'구간':<28}{'이벤트':>8}{'n10 결측':>11}{'n20 결측':>11}{'n40 결측':>11}")
SUB = [("전체 제외", X),
       ("제외 & 고점대비 -30% 이하", X[X.fromhi <= -30]),
       ("제외 & 고점대비 -50% 이하", X[X.fromhi <= -50]),
       ("제외 & 60일 수익 -20% 이하", X[X.ret60 <= -20])]
for lbl, z in SUB:
    print(f"  {lbl:<28}{len(z):>8,}"
          + "".join(f"{z[f'n{h}'].isna().mean():>10.1%}" + " " for h in (10, 20, 40)))

print("\n" + "=" * 112)
print("② 결측을 보수적으로 메우면 — 결측은 '거래가 끊겼다' 는 뜻이니 손실로 본다")
print("=" * 112)
print(f"  {'구간':<28}{'보유':>5}{'지금(결측 제외)':>16}{'결측 -50%':>12}{'결측 -100%':>13}{'결측수':>8}")
for lbl, z in SUB:
    for h in (10, 20):
        col = f"n{h}"
        cur = z[col].dropna()
        if len(cur) < 20: continue
        nmiss = int(z[col].isna().sum())
        for fill, tag in ((-50.0, "f50"), (-100.0, "f100")):
            pass
        v50 = z[col].fillna(-50.0)
        v100 = z[col].fillna(-100.0)
        print(f"  {lbl if h==10 else '':<28}{h:>4}일{cur.median():>11.2f}%(중앙)"
              f"{v50.median():>11.2f}%{v100.median():>12.2f}%{nmiss:>8,}")
        print(f"  {'':<28}{'':>5}{cur.mean():>11.2f}%(평균)"
              f"{v50.mean():>11.2f}%{v100.mean():>12.2f}%")

print("\n" + "=" * 112)
print("③ 결측 종목은 실제로 뭐였나 — 이벤트 뒤 남은 거래일 수")
print("=" * 112)
di = {d: i for i, d in enumerate(cal)}
X["left"] = X["last"].map(di) - X.date.map(di)
z = X[X.n20.isna()]
print(f"  n20 결측 {len(z):,}건 · 이벤트 뒤 남은 거래일 중앙 {z.left.median():.0f}일")
print(f"  그중 20일 미만 남은 것 {int((z.left < 20).sum()):,}건 "
      f"(= 정말 거래가 끊긴 것) · 나머지 {int((z.left >= 20).sum()):,}건은 패널 끝(최근 이벤트)")
if len(z[z.left < 20]):
    q = z[z.left < 20]
    print(f"  거래 끊긴 것들의 이벤트일 주가 중앙 {q.close.median():,.0f}원 · "
          f"고점대비 중앙 {q.fromhi.median():.0f}% · 연도 {dict(q.yr.value_counts().sort_index())}")
    print(f"  예시: " + ", ".join(f"{r['name']}({r.ticker} {r.date})" for _, r in q.head(8).iterrows()))

print("\n" + "=" * 112)
print("④ 유니버스 조건이 걸러 주는가 — 유니버스 밖 제외 이벤트의 모습")
print("=" * 112)
Y = A[A._k.isin(K)].copy()
out = Y[~Y._uni]
print(f"  유니버스 밖 {len(out):,}건 / 전체 {len(Y):,}건 ({len(out)/len(Y):.0%})")
print(f"    주가 1,000원 미만 {int((out.close < 1000).sum()):,} · "
      f"거래대금 10억 미만 {int((out.amt20.fillna(0) < 10).sum()):,} · "
      f"우선주 {int(out.pref.sum()):,} · 증자예정 {int(out.dil.fillna(False).sum()):,}")
print(f"  ▸ 유니버스 밖 이벤트의 n20 결측률 {out.n20.isna().mean():.1%} "
      f"(유니버스 안 {X.n20.isna().mean():.1%})")
