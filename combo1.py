# -*- coding: utf-8 -*-
"""1번 필터 개선안 조합 검증"""
import io, sys
import numpy as np, pandas as pd
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
P = pd.read_pickle("data/p1.pkl")
Hp = np.load("data/p1_H.npy"); Lp = np.load("data/p1_L.npy"); Cp = np.load("data/p1_C.npy")
MKT = np.load("data/p1_MKT.npy")
AMT = P.amt.values
COSTV = 0.18 + np.select([AMT >= 100, AMT >= 50, AMT >= 20, AMT >= 10], [0.20, 0.30, 0.50, 0.70], default=1.00)
GP = P.gp.values.astype(int); N = len(P)

def rets(h, sl=None, tp=None):
    Lm = Lp[:, :h+1]; Hm = Hp[:, :h+1]
    ks = np.where((Lm <= -sl).any(1), (Lm <= -sl).argmax(1), 999) if sl else np.full(N, 999)
    kt = np.where((Hm >= tp).any(1), (Hm >= tp).argmax(1), 999) if tp else np.full(N, 999)
    kk = np.minimum(np.minimum(ks, kt), h)
    r = Cp[np.arange(N), kk].astype(float)
    if sl is not None: r = np.where(ks <= np.minimum(kt, h), -float(sl), r)
    if tp is not None: r = np.where((kt < ks) & (kt <= h), float(tp), r)
    return r - COSTV, kk

def stat(m, h=10, sl=15, tp=30):
    mv = m.values if hasattr(m, "values") else m
    if mv.sum() < 15: return None
    r, kk = rets(h, sl, tp); r = r[mv]; y = P.y.values[mv]
    mk = MKT[GP[mv], np.clip(kk[mv], 0, MKT.shape[1]-1)]
    dn = r[mk <= 0]
    yy = pd.Series(r).groupby(y).mean(); cnt = pd.Series(r).groupby(y).size(); ok = yy[cnt >= 3]
    return dict(n=len(r), ret=r.mean(), med=float(np.median(r)), win=(r > 0).mean()*100,
                pf=(r[r > 0].sum()/abs(r[r <= 0].sum())) if (r <= 0).any() else 99,
                pos=f"{(ok>0).sum()}/{len(ok)}", is_=r[y <= 2022].mean(), os_=r[y >= 2023].mean(),
                dn=dn.mean() if len(dn) else np.nan, ndn=len(dn), r=r, y=y)

B = (P.quiet < 0.5) & (P.amt >= 50) & (P.ret10.between(0, 20)) & P.k20 & P.rs.notna() & (P.rs > 0) \
    & P.sr5.notna() & (P.sr5 < P.sr20)
C = [("현행", B, 10, 15, 30),
     ("A 외인 3%↑", B & (P.fwp >= 3), 10, 15, 30),
     ("B 코스피 5일선도 위", B & P.k5, 10, 15, 30),
     ("C 10일 0~10%", B & P.ret10.between(0, 10), 10, 15, 30),
     ("D 익절 +20%", B, 10, 15, 20),
     ("A+B", B & (P.fwp >= 3) & P.k5, 10, 15, 30),
     ("A+D", B & (P.fwp >= 3), 10, 15, 20),
     ("B+D", B & P.k5, 10, 15, 20),
     ("**A+B+D**", B & (P.fwp >= 3) & P.k5, 10, 15, 20),
     ("A+B+C+D", B & (P.fwp >= 3) & P.k5 & P.ret10.between(0, 10), 10, 15, 20),
     ("A+B+D · 대금 30억↑", (P.quiet < 0.5) & (P.amt >= 30) & P.ret10.between(0, 20) & P.k20 & P.k5
      & P.rs.notna() & (P.rs > 0) & P.sr5.notna() & (P.sr5 < P.sr20) & (P.fwp >= 3), 10, 15, 20),
     ("A+B+D · 손절 없음", B & (P.fwp >= 3) & P.k5, 10, None, 20),
     ("A+B+D · 15일 보유", B & (P.fwp >= 3) & P.k5, 15, 15, 20)]
print("## 1번 필터 개선안 조합 (절대수익)\n")
print("| 구성 | 건수 | **절대수익** | 중앙값 | 승률 | PF | 하락구간 | 학습(19~22) | 검증(23~26) | +연도 |")
print("|---|---|---|---|---|---|---|---|---|---|")
for lab, m, h, sl, tp in C:
    s = stat(m, h, sl, tp)
    if not s: print(f"| {lab} | 부족 |" + " - |" * 8); continue
    print(f"| {lab} | {s['n']} | **{s['ret']:+.2f}%** | {s['med']:+.2f}% | {s['win']:.0f}% | {s['pf']:.2f} | "
          f"{s['dn']:+.2f}%({s['ndn']}) | {s['is_']:+.2f}% | **{s['os_']:+.2f}%** | {s['pos']} |")
print("\n## 채택 후보 연도별 (A+B+D)\n")
s = stat(B & (P.fwp >= 3) & P.k5, 10, 15, 20)
print("| 연도 | 건수 | 절대수익 | 100만원씩 손익 | 코스피 |\n|---|---|---|---|---|")
KO = {2019: "+8%", 2020: "+31%", 2021: "+4%", 2022: "-25%", 2023: "+19%", 2024: "-10%", 2025: "+76%", 2026: "+61%"}
tot = 0
for y in range(2019, 2027):
    g = s["r"][s["y"] == y]
    if not len(g): print(f"| {y} | 0 | - | - | {KO[y]} |"); continue
    p = g.sum() / 100 * 1_000_000; tot += p
    print(f"| {y} | {len(g)} | {g.mean():+.2f}% | **{p/10000:+,.0f}만** | {KO[y]} |")
print(f"| **합계** | {s['n']} | **{s['ret']:+.2f}%** | **{tot/10000:+,.0f}만** | |")
