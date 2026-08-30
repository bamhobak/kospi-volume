# -*- coding: utf-8 -*-
"""복합 배제조건 — SG 지문(장기 지속상승 + 저변동 + 대폭상승)을 동시에 만족할 때만 배제.
   단일 임계값을 경계에 붙이는 대신, 각 축에 여유를 두고 AND 로 묶는다.
"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
X=pd.read_pickle("data/sg_x.pkl"); O=X[~X.isSG]; S=X[X.isSG]
noth=len(O)
print(f"SG 45건 지문: 1년수익 최소 {S.ret250.min():.0f}% · 20일선위 최소 {S.above20.min():.0f}% · "
      f"1년변동성 최대 {S.vol250.max():.1f}% · 1년최대낙폭 최대 {S.mdd250.max():.1f}%\n")
def ev(nm,bad):
    bad=bad.fillna(False)
    keep=X[~bad]; sg=int(keep.isSG.sum()); oth=len(keep)-sg
    a=keep[keep.y<=2022].n40.dropna(); b=keep[keep.y>=2023].n40.dropna()
    return (nm,sg,oth,oth/noth*100,a.mean(),b.mean(),(b>0).mean()*100,keep.n40.min(),int(bad.sum()))
R=[]
# 단일
R.append(ev("현행: 2년수익>100%", X.ret500>100))
R.append(ev("1년 위험조정수익>4", X.sharpe250>4))
R.append(ev("20일선위>75%", X.above20>75))
# 복합 2축
for a_ in (60,65,70): 
    for b_ in (80,100,120):
        R.append(ev(f"20일선위>{a_}% AND 1년수익>{b_}%", (X.above20>a_)&(X.ret250>b_)))
for a_ in (2,2.5,3):
    for b_ in (80,100,120):
        R.append(ev(f"위험조정>{a_} AND 1년수익>{b_}%", (X.sharpe250>a_)&(X.ret250>b_)))
# 복합 3축 (낙폭 없음 = 조정 한 번 없이 오름)
for a_ in (60,65):
    for b_ in (80,100):
        for c_ in (-15,-20):
            R.append(ev(f"20일선위>{a_}% AND 1년수익>{b_}% AND 1년최대낙폭>{c_}%",
                        (X.above20>a_)&(X.ret250>b_)&(X.mdd250>c_)))
ok=[r for r in R if r[1]==0]
ok.sort(key=lambda r:-r[3])
print("## SG 45건을 100% 배제하는 조건 — 보존율 순\n")
print("| 배제 조건 | 보존율 | 남은 신호 | 배제 건수 | 학습 | **검증** | 검증승률 | 최악 |\n|---|---|---|---|---|---|---|---|")
for nm,sg,oth,pres,am,bm,w,mn,nb in ok[:14]:
    print(f"| {nm} | **{pres:.1f}%** | {oth:,} | {nb} | {am:+.2f}% | **{bm:+.2f}%** | {w:.0f}% | {mn:.1f}% |")
bad=[r for r in R if r[1]>0]
print(f"\nSG 를 다 못 막는 조건 {len(bad)}개는 제외했습니다.")
# 여유 확인용: 최우수 후보의 각 축 여유
print("\n## 각 축의 여유 (SG 최소값 vs 임계값)\n")
print(f"- 20일선위: 임계 60~65% ← SG 최소 {S.above20.min():.1f}% (여유 {S.above20.min()-65:.1f}%p)")
print(f"- 1년수익: 임계 80~100% ← SG 최소 {S.ret250.min():.0f}% (여유 {S.ret250.min()-100:.0f}%p)")
print(f"- 정상 종목 분위: 20일선위 95% {np.percentile(O.above20.dropna(),95):.1f}% · 1년수익 95% {np.percentile(O.ret250.dropna(),95):.0f}%")
