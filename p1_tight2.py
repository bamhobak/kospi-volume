# -*- coding: utf-8 -*-
"""강화 조합 — 건수 1/3~1/5 로 줄이면서 안전성 지표를 올린다"""
import io,sys,itertools,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/bull_feat.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
g=D.groupby("ticker",sort=False)
D["ret250"]=g.close.transform(lambda x:x/x.shift(250)-1)*100
D["above20"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
BASE=(((D.fromhi>=-10)&(D.r16<120)&(D.rw1<=120)&(D.fw5>=3)&(D.fw60>=1)&(D.vol20<=3)
      &(D.sr20<=1)&(D.ret20<=10)&(D.amt20>=50)&(~D.dil)).fillna(False)
      & ~((D.above20>70)&(D.ret250>120)).fillna(False))
X=D[BASE].copy(); N0=len(X)
OPT={
 "저점대비≤30":X.fromlo<=30, "변동성≤2":X.vol20<=2, "거래대금≥200억":X.amt20>=200,
 "외인5일≥7":X.fw5>=7, "공매도≤0.5":X.sr20<=0.5, "상승장만":X.k60, "20일수익≤5":X.ret20<=5,
}
rows=[]
for k in range(1,5):
    for c in itertools.combinations(OPT,k):
        m=pd.Series(True,index=X.index)
        for n in c: m&=OPT[n].fillna(False)
        s=X[m]
        if not (250<=len(s)<=900): continue
        a=s[s.y<=2022].n40.dropna(); b=s[s.y>=2023].n40.dropna()
        if len(a)<80 or len(b)<80: continue
        r=b.values; pf=r[r>0].sum()/abs(r[r<=0].sum())
        rows.append((" + ".join(c),len(s),len(s)/N0*100,a.mean(),r.mean(),np.median(r),
                     (r>0).mean()*100,pf,np.percentile(r,5),r.min()))
print(f"조건 {len(OPT)}개 조합 중 건수 250~900 구간 {len(rows)}개\n")
print("## 학습기간 수익 상위 (선별은 학습으로만)\n")
print("| 조합 | 건수 | 보존 | 학습 | **검증** | 중앙값 | 승률 | PF | 하위5% | 최악 |\n|---|---|---|---|---|---|---|---|---|---|")
for r in sorted(rows,key=lambda x:-x[3])[:10]:
    print(f"| {r[0]} | {r[1]} | {r[2]:.0f}% | **{r[3]:+.2f}%** | {r[4]:+.2f}% | {r[5]:+.2f}% | {r[6]:.0f}% | {r[7]:.2f} | {r[8]:.1f}% | {r[9]:.0f}% |")
print("\n## 안전성 상위 — 학습·검증 둘 다 승률 55%↑ · 최악 -25% 이내\n")
safe=[r for r in rows if r[6]>=55 and r[9]>=-25]
print("| 조합 | 건수 | 보존 | 학습 | **검증** | 중앙값 | 승률 | PF | 하위5% | 최악 |\n|---|---|---|---|---|---|---|---|---|---|")
for r in sorted(safe,key=lambda x:-x[3])[:12]:
    print(f"| {r[0]} | {r[1]} | {r[2]:.0f}% | **{r[3]:+.2f}%** | {r[4]:+.2f}% | {r[5]:+.2f}% | {r[6]:.0f}% | {r[7]:.2f} | {r[8]:.1f}% | {r[9]:.0f}% |")
