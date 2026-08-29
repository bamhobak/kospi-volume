# -*- coding: utf-8 -*-
"""2번 필터 개선안 조합 검증"""
import io, sys
import numpy as np, pandas as pd
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
P = pd.read_pickle("data/p1.pkl")
Hp = np.load("data/p1_H.npy"); Lp = np.load("data/p1_L.npy"); Cp = np.load("data/p1_C.npy")
MKT = np.load("data/p1_MKT.npy")
AMT = P.amt.values
COSTV = 0.18 + np.select([AMT >= 100, AMT >= 50, AMT >= 20, AMT >= 10], [0.20, 0.30, 0.50, 0.70], default=1.00)
GP = P.gp.values.astype(int); N = len(P)
SRD = P.sr5.notna() & P.sr20.notna() & (P.sr5 < P.sr20)

def rets(h, sl=None, tp=None):
    Lm = Lp[:, :h+1]; Hm = Hp[:, :h+1]
    ks = np.where((Lm <= -sl).any(1), (Lm <= -sl).argmax(1), 999) if sl else np.full(N, 999)
    kt = np.where((Hm >= tp).any(1), (Hm >= tp).argmax(1), 999) if tp else np.full(N, 999)
    kk = np.minimum(np.minimum(ks, kt), h)
    r = Cp[np.arange(N), kk].astype(float)
    if sl is not None: r = np.where(ks <= np.minimum(kt, h), -float(sl), r)
    if tp is not None: r = np.where((kt < ks) & (kt <= h), float(tp), r)
    return r - COSTV, kk
def stat(m, h=10, sl=None, tp=None, mn=12):
    mv = m.values if hasattr(m, "values") else m
    if mv.sum() < mn: return None
    r, kk = rets(h, sl, tp); r = r[mv]; y = P.y.values[mv]
    mk = MKT[GP[mv], np.clip(kk[mv], 0, MKT.shape[1]-1)]
    dn = r[mk <= 0]
    yy = pd.Series(r).groupby(y).mean(); cnt = pd.Series(r).groupby(y).size(); ok = yy[cnt >= 3]
    return dict(n=len(r), ret=r.mean(), med=float(np.median(r)), win=(r > 0).mean()*100,
                pf=(r[r > 0].sum()/abs(r[r <= 0].sum())) if (r <= 0).any() else 99,
                pos=f"{(ok>0).sum()}/{len(ok)}", is_=r[y <= 2022].mean(), os_=r[y >= 2023].mean(),
                dn=dn.mean() if len(dn) else np.nan, ndn=len(dn), r=r, y=y)

B = (P.quiet < 0.3) & (P.amt >= 3) & (P.ret3 <= -5) & SRD & (~P.dil)
C = [("현행", B),
     ("**A 코스피 20일선 아래**", B & ~P.k20),
     ("B 기관도 순매수", B & (P.owp > 0)),
     ("C 10일도 하락", B & (P.ret10 <= 0)),
     ("D 3일 -7%↓", (P.quiet < 0.3) & (P.amt >= 3) & (P.ret3 <= -7) & SRD & (~P.dil)),
     ("A+B", B & ~P.k20 & (P.owp > 0)),
     ("A+C", B & ~P.k20 & (P.ret10 <= 0)),
     ("A+D", (P.quiet < 0.3) & (P.amt >= 3) & (P.ret3 <= -7) & SRD & (~P.dil) & ~P.k20),
     ("A+B+C", B & ~P.k20 & (P.owp > 0) & (P.ret10 <= 0)),
     ("A+C+D", (P.quiet < 0.3) & (P.amt >= 3) & (P.ret3 <= -7) & SRD & (~P.dil) & ~P.k20 & (P.ret10 <= 0)),
     ("A · 공매도 조건 제거", (P.quiet < 0.3) & (P.amt >= 3) & (P.ret3 <= -5) & (~P.dil) & ~P.k20),
     ("A · 잠잠<0.4", (P.quiet < 0.4) & (P.amt >= 3) & (P.ret3 <= -5) & SRD & (~P.dil) & ~P.k20),
     ("A · 60일선 아래로 대체", B & (P.dev60 < 0))]
print("## 2번 필터 개선안 조합 (절대수익 · 10일 보유 · 손절/익절 없음)\n")
print("| 구성 | 건수 | **절대수익** | 중앙값 | 승률 | PF | 하락구간 | 학습(19~22) | 검증(23~26) | +연도 |")
print("|---|---|---|---|---|---|---|---|---|---|")
for lab, m in C:
    s = stat(m)
    if not s: print(f"| {lab} | 부족 |" + " - |" * 8); continue
    print(f"| {lab} | {s['n']} | **{s['ret']:+.2f}%** | {s['med']:+.2f}% | {s['win']:.0f}% | {s['pf']:.2f} | "
          f"{s['dn']:+.2f}%({s['ndn']}) | {s['is_']:+.2f}% | **{s['os_']:+.2f}%** | {s['pos']} |")

print("\n## 후보별 연도별 절대수익 · 100만원씩 손익\n")
KO = {2019: "+8%", 2020: "+31%", 2021: "+4%", 2022: "-25%", 2023: "+19%", 2024: "-10%", 2025: "+76%", 2026: "+61%"}
for lab, m in [("현행", B), ("A 코스피 20일선 아래", B & ~P.k20), ("A+B (기관 순매수 추가)", B & ~P.k20 & (P.owp > 0))]:
    s = stat(m)
    print(f"\n**{lab}** — {s['n']}건 · 평균 {s['ret']:+.2f}%\n")
    print("| 연도 | 건수 | 절대수익 | 100만원씩 | 코스피 |\n|---|---|---|---|---|")
    tot = 0
    for y in range(2019, 2027):
        g = s["r"][s["y"] == y]
        if not len(g): print(f"| {y} | 0 | - | - | {KO[y]} |"); continue
        p = g.sum() / 100 * 1_000_000; tot += p
        print(f"| {y} | {len(g)} | {g.mean():+.2f}% | **{p/10000:+,.0f}만** | {KO[y]} |")
    print(f"| **합계** | {s['n']} | {s['ret']:+.2f}% | **{tot/10000:+,.0f}만** | |")
