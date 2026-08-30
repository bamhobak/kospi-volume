# -*- coding: utf-8 -*-
"""코스닥 새 규칙 탐색 2 — 조합 (학습에서만 선별, 안정성 기준)"""
import io,sys,itertools,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/kd_feat.pkl")
SAFE=((D.close>=1000)&(~D.dil)&(D.amt20>=5)&(D.ret500<=100)).fillna(False)
X=D[SAFE].copy()
OPT={
 "신고가-10이내":X.fromhi>=-10,"거래량침체r16<80":X.r16<80,"단기잠잠rw1≤120":X.rw1<=120,
 "외인5일≥5":X.fw5>=5,"외인60일≥1":X.fw60>=1,"변동성≤3":X.vol20<=3,
 "공매도≤0.5":X.sr20<=0.5,"20일수익≤5":X.ret20<=5,"거래대금≥20억":X.amt20>=20,
 "코스닥60일선위":X.q60,"기관20일≥0":X.ow20>=0,
}
res=[]
for k in (3,4,5):
    for c in itertools.combinations(OPT,k):
        m=pd.Series(True,index=X.index)
        for n in c: m&=OPT[n].fillna(False)
        s=X[m]
        a=s[s.y<=2022]; b=s[s.y>=2023]
        if not (150<=len(s)<=2500) or len(a)<60 or len(b)<50: continue
        for h in (20,40):
            ra=a[f"n{h}"].dropna().values; rb=b[f"n{h}"].dropna().values
            if len(ra)<60 or len(rb)<50: continue
            if (ra>0).mean()<0.55: continue         # 학습 승률 55% 미만 기각
            pf=rb[rb>0].sum()/abs(rb[rb<=0].sum()) if (rb<=0).any() else 99
            res.append((" + ".join(c),h,len(s),ra.mean(),(ra>0).mean()*100,np.median(ra),
                        rb.mean(),(rb>0).mean()*100,np.median(rb),pf,np.percentile(rb,5),rb.min()))
print(f"학습 승률 55%↑ 통과 조합 {len(res)}개\n")
if not res:
    print("**해당 없음** — 코스닥 상승장에서 학습 승률 55% 를 넘는 조합이 없습니다.")
else:
    res.sort(key=lambda r:-r[4])
    print("## 학습 승률 상위 12 (선별은 학습으로만)\n")
    print("| 조합 | 보유 | 건수 | 학습평균 | **학습승률** | 검증평균 | 검증승률 | 검증중앙 | PF | 하위5% |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in res[:12]:
        print(f"| {r[0]} | {r[1]}일 | {r[2]} | {r[3]:+.2f}% | **{r[4]:.0f}%** | {r[6]:+.2f}% | {r[7]:.0f}% | {r[8]:+.2f}% | {r[9]:.2f} | {r[10]:.1f}% |")
    ok=[r for r in res if r[7]>=55]
    print(f"\n검증에서도 승률 55%↑ 유지: **{len(ok)}/{len(res)}개**")
