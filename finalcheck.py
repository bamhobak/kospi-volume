# -*- coding: utf-8 -*-
"""① 2번 필터 3일 급락 임계값 안정성 ② 1번 필터 절대수익 기준 재실측"""
import io, sys
import numpy as np, pandas as pd
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
P = pd.read_pickle("data/pool_abs.pkl")
P["f2base"] = (P.quiet < 0.3) & (P.amt >= 3) & P.srd & (~P.dil)
YS = list(range(2019, 2027))

def st(d, col):
    if len(d) < 8: return None
    r = d[col]
    yy = d.groupby("y")[col].mean(); cnt = d.groupby("y").size(); ok = yy[cnt >= 3]
    return dict(n=len(r), ret=r.mean(), med=r.median(), win=(r > 0).mean() * 100,
                pf=(r[r > 0].sum() / abs(r[r <= 0].sum())) if (r <= 0).any() else 99,
                pos=f"{(ok>0).sum()}/{len(ok)}",
                is_=d[d.y <= 2022][col].mean(), os_=d[d.y >= 2023][col].mean(),
                nis=len(d[d.y <= 2022]), nos=len(d[d.y >= 2023]),
                dn=d[d.mk <= 0][col].mean() if (d.mk <= 0).any() else np.nan,
                ndn=int((d.mk <= 0).sum()))

print("# ① 2번 필터 — 3일 급락 임계값 안정성\n")
print("| 임계값 | 건수 | 절대수익 | 중앙값 | 승률 | PF | 하락구간 | 학습(19~22) | 검증(23~26) | +연도 |")
print("|---|---|---|---|---|---|---|---|---|---|")
b = P[P.f2base]
for th in (0, -1, -2, -3, -4, -5, -6, -8, -10):
    s = st(b[b.ret3 <= th], "r2")
    if s: print(f"| 3일 {th}%↓ | {s['n']} | **{s['ret']:+.2f}%** | {s['med']:+.2f}% | {s['win']:.0f}% | {s['pf']:.2f} | "
                f"{s['dn']:+.2f}%({s['ndn']}) | {s['is_']:+.2f}%({s['nis']}) | **{s['os_']:+.2f}%**({s['nos']}) | {s['pos']} |")
print("\n## 연도별 (임계값별)\n")
print("| 임계값 | " + " | ".join(str(y) for y in YS) + " |\n|---|" + "---|" * len(YS))
for th in (0, -3, -5, -8):
    d = b[b.ret3 <= th]; c = []
    for y in YS:
        g = d[d.y == y]; c.append(f"{g.r2.mean():+.1f}({len(g)})" if len(g) >= 3 else f"-({len(g)})")
    print(f"| 3일 {th}%↓ | " + " | ".join(c) + " |")

print("\n\n# ② 1번 필터 — 절대수익 기준 재실측\n")
f1 = (P.quiet < 0.5) & (P.amt >= 50) & (P.ret10.between(0, 20)) & P.k20 & P.rs.notna() & (P.rs > 0)
print("## 현행 조건 · 청산 방식 비교\n")
print("| 청산 | 건수 | 절대수익 | 중앙값 | 승률 | PF | 하락구간 | 학습 | 검증 | +연도 |\n|---|---|---|---|---|---|---|---|---|---|")
for col, lab in (("r1", "10일·손절15·익절30 (현행)"), ("r2", "10일·손절/익절 없음")):
    s = st(P[f1], col)
    print(f"| {lab} | {s['n']} | **{s['ret']:+.2f}%** | {s['med']:+.2f}% | {s['win']:.0f}% | {s['pf']:.2f} | "
          f"{s['dn']:+.2f}%({s['ndn']}) | {s['is_']:+.2f}% | **{s['os_']:+.2f}%** | {s['pos']} |")
print("\n## 조건별 (청산: 손절15·익절30 유지)\n")
print("| 변경 | 건수 | 절대수익 | 중앙값 | 승률 | PF | 하락구간 | +연도 |\n|---|---|---|---|---|---|---|---|")
VAR = [
    ("현행", f1),
    ("코스피 20일선 조건 제거", (P.quiet < 0.5) & (P.amt >= 50) & (P.ret10.between(0, 20)) & P.rs.notna() & (P.rs > 0)),
    ("업종 상대강도 제거", (P.quiet < 0.5) & (P.amt >= 50) & (P.ret10.between(0, 20)) & P.k20),
    ("둘 다 제거", (P.quiet < 0.5) & (P.amt >= 50) & (P.ret10.between(0, 20))),
    ("대금 30억↑", (P.quiet < 0.5) & (P.amt >= 30) & (P.ret10.between(0, 20)) & P.k20 & P.rs.notna() & (P.rs > 0)),
    ("대금 100억↑", (P.quiet < 0.5) & (P.amt >= 100) & (P.ret10.between(0, 20)) & P.k20 & P.rs.notna() & (P.rs > 0)),
    ("잠잠<0.3", (P.quiet < 0.3) & (P.amt >= 50) & (P.ret10.between(0, 20)) & P.k20 & P.rs.notna() & (P.rs > 0)),
    ("10일 0~10%", (P.quiet < 0.5) & (P.amt >= 50) & (P.ret10.between(0, 10)) & P.k20 & P.rs.notna() & (P.rs > 0)),
    ("10일 상승 조건 제거", (P.quiet < 0.5) & (P.amt >= 50) & P.k20 & P.rs.notna() & (P.rs > 0)),
    ("★10일 하락으로 반전", (P.quiet < 0.5) & (P.amt >= 50) & (P.ret10 <= 0) & P.k20 & P.rs.notna() & (P.rs > 0)),
    ("★3일 -5%↓ 추가", f1 & (P.ret3 <= -5)),
    ("공매도 감소 추가", f1 & P.srd),
    ("유상증자 90일 제외", f1 & (~P.dil)),
]
for lab, m in VAR:
    s = st(P[m], "r1")
    if s: print(f"| {lab} | {s['n']} | **{s['ret']:+.2f}%** | {s['med']:+.2f}% | {s['win']:.0f}% | {s['pf']:.2f} | {s['dn']:+.2f}%({s['ndn']}) | {s['pos']} |")
print("\n## 1번 필터 연도별 (현행 · 손절15·익절30)\n")
d = P[f1]; c = []
for y in YS:
    g = d[d.y == y]; c.append(f"{g.r1.mean():+.1f}({len(g)})" if len(g) >= 3 else f"-({len(g)})")
print("| 1번 현행 | " + " | ".join(c) + " |")
print("| 코스피   | +8% | +31% | +4% | -25% | +19% | -10% | +76% | +61% |")
