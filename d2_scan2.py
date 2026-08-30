# -*- coding: utf-8 -*-
"""코스닥에서 도달 가능한 최대 안정성 — 국면·보유기간 무제한 탐색"""
import io,sys,itertools,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/kd_feat.pkl")
SAFE=((D.close>=1000)&(~D.dil)&(D.amt20>=5)&(D.ret500<=100)).fillna(False)
X=D[SAFE].copy()
OPT={
 "신고가-10이내":X.fromhi>=-10,"거래량침체r16<80":X.r16<80,"단기잠잠rw1≤120":X.rw1<=120,
 "외인5일≥5":X.fw5>=5,"외인60일≥1":X.fw60>=1,"변동성≤3":X.vol20<=3,
 "공매도≤0.5":X.sr20<=0.5,"20일수익≤5":X.ret20<=5,"거래대금≥20억":X.amt20>=20,
 "코스닥60일선위":X.q60,"코스닥60일선아래":~X.q60,"코스피60일선아래":~X.k60,
 "기관20일≥0":X.ow20>=0,"20일수익≤-20":X.ret20<=-20,"당일거래량2배":X.su1>=2,
 "20일선이격≤-10":X.dma20<=-10,"공매도감소":X.srd==True,
}
res=[]
for k in (3,4,5):
    for c in itertools.combinations(OPT,k):
        if "코스닥60일선위" in c and "코스닥60일선아래" in c: continue
        m=pd.Series(True,index=X.index)
        for n in c: m&=OPT[n].fillna(False)
        s=X[m]
        if not (120<=len(s)<=3000): continue
        a=s[s.y<=2022]; b=s[s.y>=2023]
        for h in (10,20,40):
            ra=a[f"n{h}"].dropna().values; rb=b[f"n{h}"].dropna().values
            if len(ra)<60 or len(rb)<40: continue
            res.append((" + ".join(c),h,len(s),len(ra),(ra>0).mean()*100,ra.mean(),np.median(ra),
                        len(rb),(rb>0).mean()*100,rb.mean(),np.median(rb),np.percentile(rb,5)))
print(f"평가 조합 {len(res):,}개\n")
res.sort(key=lambda r:-r[4])
print("## 학습 승률 상위 15 (선별은 학습으로만)\n")
print("| 조합 | 보유 | 학습건수 | **학습승률** | 학습중앙 | 검증건수 | **검증승률** | 검증중앙 | 검증평균 |")
print("|---|---|---|---|---|---|---|---|---|")
for r in res[:15]:
    print(f"| {r[0]} | {r[1]}일 | {r[3]} | **{r[4]:.0f}%** | {r[6]:+.1f}% | {r[7]} | **{r[8]:.0f}%** | {r[10]:+.1f}% | {r[9]:+.2f}% |")
top=[r for r in res if r[4]>=55]
print(f"\n학습 승률 55%↑: {len(top)}개 · 그중 검증도 55%↑: {len([r for r in top if r[8]>=55])}개")
print(f"학습 승률 최대: {max(r[4] for r in res):.0f}%")
print("\n## 국면별 최고 승률\n")
for lab,key in [("코스닥 상승장","코스닥60일선위"),("코스닥 하락장","코스닥60일선아래"),("코스피 하락장","코스피60일선아래")]:
    sub=[r for r in res if key in r[0]]
    if sub:
        b=max(sub,key=lambda r:r[4])
        print(f"- **{lab}**: 최고 학습승률 {b[4]:.0f}% (검증 {b[8]:.0f}%) — {b[0]} / {b[1]}일")
