# -*- coding: utf-8 -*-
"""업종 조건이 현행 3번 신호의 '부분집합'인지 확인 + 업종 데이터 없는 신호 처리"""
import io, sys
import numpy as np, pandas as pd
exec(open("f3_sector.py", encoding="utf-8").read().split("HAS = D.sret60.notna()")[0])

HAS = D.sret60.notna()
base = set(zip(D[F3].ticker, D[F3].date))
print(f"\n## 부분집합 확인\n")
print(f"- 현행 3번 신호: **{len(base)}건**")
for th in (-5, -10, -15, -20):
    m = F3 & HAS & (D.sret60 <= th)
    s = set(zip(D[m].ticker, D[m].date))
    print(f"- 업종 {th}% 조건 추가: **{len(s)}건** · 현행에 포함되는가 → "
          f"{'예 (100% 부분집합)' if s <= base else '아니오'} · 새로 생긴 신호 {len(s - base)}건")

print(f"\n## 걸러지는 {len(base) - int((F3 & HAS & (D.sret60 <= -10)).sum())}건의 내역 (업종 -10% 기준)\n")
no = F3 & ~HAS                       # 업종 수익률을 계산할 수 없는 신호
yes_out = F3 & HAS & (D.sret60 > -10)
print(f"| 구분 | 건수 | 절대수익 | 중앙값 | 승률 | 학습 | 검증 |")
print("|---|---|---|---|---|---|---|")
for lab, m in [("① 업종 데이터 없음 (매핑X·회원5개 미만)", no),
               ("② 업종은 있으나 -10% 초과 (덜 빠짐)", yes_out),
               ("③ 남는 신호 (업종 -10% 이하)", F3 & HAS & (D.sret60 <= -10))]:
    s = ev(m)
    if s: print(f"| {lab} | {s['n']} | **{s['ret']:+.2f}%** | {s['med']:+.2f}% | {s['win']:.0f}% | {s['is_']:+.2f}% | **{s['os_']:+.2f}%** |")
    else: print(f"| {lab} | {int(m.fillna(False).sum())} | 10건 미만 | - | - | - | - |")

print("\n## 업종 데이터 없는 신호는 살릴까 버릴까 (업종 -10% 기준)\n")
print(HDR)
row("현행 3번 (조건 없음)", F3)
row("업종 -10%↓ · 데이터 없으면 **제외**", F3 & HAS & (D.sret60 <= -10))
row("업종 -10%↓ · 데이터 없으면 **통과**", F3 & (~HAS | (D.sret60 <= -10)))

print("\n## 업종 데이터가 없는 이유\n")
x = D[F3 & ~HAS]
print(f"- 총 {len(x)}건 · {x.ticker.nunique()}종목")
print(f"- 업종 매핑 자체가 없음: {int(x.up.isna().sum())}건")
print(f"- 업종은 있으나 회원 5종목 미만: {int((x.up.notna()).sum())}건")
if x.up.notna().any():
    print("  해당 업종:", ", ".join(f"{g}({n})" for g, n in x[x.up.notna()].up.value_counts().head(8).items()))
print(f"- 폐지 종목: {int((x.grp=='폐지').sum())}건")
