# -*- coding: utf-8 -*-
"""코스닥 새 규칙 탐색 1 — 안정성 기준 단일조건 (학습 2018~22 만)
   평가축: 승률 · 중앙값 · 하위5% (평균이 아니라)
"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/kd_feat.pkl")
# 공통 안전판: 주가 1,000원 이상 · 증자 없음 · 최소 유동성
SAFE=((D.close>=1000)&(~D.dil)&(D.amt20>=5)).fillna(False)
IS=D[SAFE&(D.y<=2022)]
print(f"안전판 적용 학습 표본 {len(IS):,}행\n")
print("## 기준선 — 아무 코스닥 종목 (안전판만)\n")
print("| 국면 | 보유 | 평균 | 중앙값 | 승률 | 하위5% |\n|---|---|---|---|---|---|")
for lab,m in [("전체",pd.Series(True,index=IS.index)),("코스닥 60일선 위",IS.q60),("아래",~IS.q60)]:
    for h in (20,40):
        r=IS[m][f"n{h}"].dropna()
        print(f"| {lab} | {h}일 | {r.mean():+.2f}% | {np.median(r):+.2f}% | {(r>0).mean()*100:.0f}% | {np.percentile(r,5):.1f}% |")
B=IS[IS.q60]     # 코스닥 상승장
print(f"\n## 상승장(코스닥 60일선 위) 단일조건 · 40일 보유 — 승률 순\n")
base=B.n40.dropna()
print(f"기준선: 승률 {(base>0).mean()*100:.0f}% · 중앙값 {np.median(base):+.2f}% · 평균 {base.mean():+.2f}%\n")
C=[]
a=lambda nm,s:C.append((nm,s))
for q in (-10,-5,-3): a(f"신고가 {q}% 이내",B.fromhi>=q)
for q in (50,80,120): a(f"거래량침체 r16<{q}",B.r16<q)
for q in (80,120): a(f"단기거래량 rw1≤{q}",B.rw1<=q)
for q in (3,5,10): a(f"외인5일≥{q}%",B.fw5>=q)
for q in (1,2,3): a(f"외인60일≥{q}%",B.fw60>=q)
for q in (0,1,2): a(f"기관20일≥{q}%",B.ow20>=q)
for q in (2,3,4): a(f"변동성≤{q}%",B.vol20<=q)
for q in (0.5,1,2): a(f"공매도비중≤{q}%",B.sr20<=q)
a("공매도 감소",B.srd==True)
for q in (0,5,10): a(f"20일수익≤{q}%",B.ret20<=q)
for q in (-10,-20): a(f"20일수익≤{q}%",B.ret20<=q)
for q in (10,30,50,100,200): a(f"거래대금≥{q}억",B.amt20>=q)
for q in (30,50,100): a(f"저점대비≤+{q}%",B.fromlo<=q)
for q in (100,200): a(f"2년수익≤{q}%",B.ret500<=q)
for q in (0,5): a(f"20일선이격≥{q}%",B.dma20>=q)
for q in (-5,-10): a(f"20일선이격≤{q}%",B.dma20<=q)
a("코스피도 60일선 위",B.k60)
a("종가위치 clv≥0.7",B.clv>=0.7)
R=[]
for nm,s in C:
    x=B[s.fillna(False)].n40.dropna()
    if len(x)<400: continue
    R.append((nm,len(x),x.mean(),np.median(x),(x>0).mean()*100,np.percentile(x,5)))
R.sort(key=lambda r:-r[4])
print("| 조건 | 표본 | 평균 | 중앙값 | **승률** | 하위5% |\n|---|---|---|---|---|---|")
for nm,n,m,md,w,p5 in R[:16]:
    print(f"| {nm} | {n:,} | {m:+.2f}% | {md:+.2f}% | **{w:.0f}%** | {p5:.1f}% |")
print("\n**승률 하위 5개**\n")
for nm,n,m,md,w,p5 in R[-5:]:
    print(f"- {nm}: 승률 {w:.0f}% · 중앙 {md:+.2f}%")
