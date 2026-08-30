# -*- coding: utf-8 -*-
"""2단계: 기준선 + 단일조건 한계효과 (학습기간 2018~2022 만 사용)"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/bull_feat.pkl")
IS=D[(D.y<=2022)]; OS=D[(D.y>=2023)]
print(f"학습 {len(IS):,}행 (2018~22) · 검증 {len(OS):,}행 (2023~26)\n")

print("## 기준선 — 상승장에서 아무 코스피 종목이나 매수\n")
print("| 국면 | 보유 | 표본 | 절대수익 | **알파(지수대비)** | 알파승률 |")
print("|---|---|---|---|---|---|")
for lab,m in [("전체",np.ones(len(IS),bool)),("60일선 위",IS.k60.values),
              ("60일선 위 + 20일선 위",(IS.k60&IS.k20).values),("60일선 아래",~IS.k60.values)]:
    for h in (10,20,40):
        x=IS[m]; a=x[f"a{h}"].dropna(); n=x[f"n{h}"].dropna()
        print(f"| {lab} | {h}일 | {len(a):,} | {n.mean():+.2f}% | **{a.mean():+.2f}%** | {(a>0).mean()*100:.0f}% |")
print("\n※ 알파 기준선이 음수인 것은 비용(0.18~1.18%) 때문. 규칙은 이걸 넘어야 의미가 있다.\n")

# ── 단일조건 한계효과 (상승장 = 60일선 위, 보유 20일) ─────────
B=IS[IS.k60].copy()
base=B["a20"].mean(); print(f"## 단일조건 한계효과 — 상승장·20일 보유 (기준선 알파 {base:+.2f}%)\n")
CONDS=[]
def add(nm,s): CONDS.append((nm,s))
for q in (10,20,30): add(f"거래량침체 r16<{q*5}", B.r16<q*5)
for q in (150,200,300,500): add(f"거래량급증 rw1>={q}", B.rw1>=q)
for q in (2,3,5): add(f"당일거래량 su1>={q}", B.su1>=q)
for q in (1,2,3,5): add(f"외국인5일 fw5>={q}", B.fw5>=q)
for q in (0.5,1,2): add(f"외국인60일 fw60>={q}", B.fw60>=q)
for q in (1,2,3): add(f"기관5일 ow5>={q}", B.ow5>=q)
for q in (-20,-10,-5,0): add(f"20일수익 ret20<={q}", B.ret20<=q)
for q in (0,5,10,20): add(f"20일수익 ret20>={q}", B.ret20>=q)
for q in (-30,-20,-10,0): add(f"60일수익 ret60<={q}", B.ret60<=q)
for q in (0,10,20): add(f"60일수익 ret60>={q}", B.ret60>=q)
for q in (-10,-5,0): add(f"20일선이격 dma20<={q}", B.dma20<=q)
for q in (0,5): add(f"20일선이격 dma20>={q}", B.dma20>=q)
for q in (-5,0,5): add(f"60일선이격 dma60>={q}", B.dma60>=q)
for q in (-50,-40,-30,-20,-10): add(f"고점대비 fromhi<={q}", B.fromhi<=q)
for q in (-5,-2): add(f"고점근접 fromhi>={q}", B.fromhi>=q)
for q in (10,20,50): add(f"저점대비 fromlo<={q}", B.fromlo<=q)
for q in (3,5,10,20,50,100): add(f"거래대금 amt20>={q}억", B.amt20>=q)
for q in (10,20,50): add(f"거래대금 amt20<={q}억", B.amt20<=q)
for q in (2,3,5): add(f"변동성 vol20<={q}", B.vol20<=q)
for q in (3,5): add(f"변동성 vol20>={q}", B.vol20>=q)
add("공매도감소 srd", B.srd==True); add("공매도증가", B.srd==False)
add("증자없음", ~B.dil); add("증자있음", B.dil)
add("종가위치 clv>=0.7", B.clv>=0.7); add("종가위치 clv<=0.3", B.clv<=0.3)
for q in (-3,0,3): add(f"익일갭 gap<={q}", B.gap<=q)
add("20일선 위(지수)", B.k20); add("20일선 아래(지수)", ~B.k20)
add("120일선 위(지수)", B.k120)

rows=[]
for nm,s in CONDS:
    s=s.fillna(False) if hasattr(s,"fillna") else s
    x=B[s][["a20","n20"]].dropna()
    if len(x)<300: continue
    rows.append((nm,len(x),x.a20.mean(),x.a20.mean()-base,(x.a20>0).mean()*100,x.n20.mean()))
rows.sort(key=lambda r:-r[3])
print("| 조건 | 표본 | 알파 | **한계효과** | 알파승률 | 절대수익 |\n|---|---|---|---|---|---|")
for nm,n,a,d,w,ab in rows[:22]:
    print(f"| {nm} | {n:,} | {a:+.2f}% | **{d:+.2f}%p** | {w:.0f}% | {ab:+.2f}% |")
print("\n**하위 5개(역효과)**\n\n| 조건 | 표본 | 알파 | 한계효과 |\n|---|---|---|---|")
for nm,n,a,d,w,ab in rows[-5:]:
    print(f"| {nm} | {n:,} | {a:+.2f}% | {d:+.2f}%p |")
