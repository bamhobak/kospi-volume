# -*- coding: utf-8 -*-
"""SG 배제 조건 후보 비교 — 100% 제거하면서 신호 손실 최소화"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
X=pd.read_pickle("data/sg_x.pkl")
S=X.isSG.values; base=len(X); nsg=int(S.sum()); noth=base-nsg
print(f"가드 없는 P4: {base:,}건 (SG {nsg}건 + 나머지 {noth:,}건)")
print(f"가드 없을 때 학습 {X[X.y<=2022].n40.mean():+.2f}% · 검증 {X[X.y>=2023].n40.mean():+.2f}% · 최악 {X.n40.min():.1f}%\n")
CAND=[]
for q in (100,150,200,240): CAND.append((f"2년수익 ≤ {q}%", X.ret500<=q))
for q in (100,120,125): CAND.append((f"1년수익 ≤ {q}%", X.ret250<=q))
for q in (2.5,3,4,5): CAND.append((f"1년 위험조정수익 ≤ {q}", X.sharpe250<=q))
for q in (3,4,5,15): CAND.append((f"2년 위험조정수익 ≤ {q}", X.sharpe500<=q))
for q in (70,75,77): CAND.append((f"20일선 위 비율 ≤ {q}%", X.above20<=q))
for q in (120,150,200): CAND.append((f"저점대비 ≤ +{q}%", X.fromlo<=q))
CAND.append(("1년최대낙폭 ≤ -10%", X.mdd250<=-10))
CAND.append(("현행: 2년≤100%", X.ret500<=100))
print("| 조건 | SG 제거 | 남은 신호 | 보존율 | 학습수익 | **검증수익** | 검증승률 | 최악 |")
print("|---|---|---|---|---|---|---|---|")
rows=[]
for nm,m in CAND:
    m=m.fillna(True)                       # 데이터 없으면 통과(현행 규약과 동일)
    keep=X[m]; sgleft=int((keep.isSG).sum())
    oth=len(keep)-sgleft
    a=keep[keep.y<=2022].n40.dropna(); b=keep[keep.y>=2023].n40.dropna()
    if not len(b): continue
    rows.append((nm,sgleft,len(keep),oth/noth*100,a.mean(),b.mean(),(b>0).mean()*100,keep.n40.min()))
for nm,sg,n,pres,am,bm,w,mn in rows:
    tag="**전부 제거**" if sg==0 else f"{sg}건 남음"
    print(f"| {nm} | {tag} | {n:,} | {pres:.0f}% | {am:+.2f}% | **{bm:+.2f}%** | {w:.0f}% | {mn:.1f}% |")
print("\n## SG 를 100% 제거하는 조건만, 보존율 순\n")
ok=sorted([r for r in rows if r[1]==0], key=lambda r:-r[3])
print("| 조건 | 보존율 | 남은 신호 | 학습 | **검증** | 최악 |\n|---|---|---|---|---|---|")
for nm,sg,n,pres,am,bm,w,mn in ok:
    print(f"| {nm} | **{pres:.0f}%** | {n:,} | {am:+.2f}% | **{bm:+.2f}%** | {mn:.1f}% |")
