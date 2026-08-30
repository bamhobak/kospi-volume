# -*- coding: utf-8 -*-
"""1) 기관 조건이 기존 D1 을 개선하는가  2) 코스닥 조정매집(P2 코스닥판) 규칙이 있는가"""
import io,sys,csv,itertools,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/kd_feat.pkl")
IND={}
for r in csv.DictReader(open("data/industry.csv",encoding="utf-8-sig")):
    k=list(r.values()); IND[k[0]]=k[-1]
D["up"]=D.ticker.map(IND)
u=D[D.up.notna()].dropna(subset=["ret60"]).groupby(["date","up"]).ret60.median()
D["sr60"]=pd.MultiIndex.from_arrays([D.date,D.up]).map(u)
D1=((D.ret20<=-20)&(D.su1>=2)&(D.fw60>=1)&(D.amt20>=2)&(~D.k60)
    &(D.sr60.isna()|(D.sr60<=-15))&(D.srd==True)&(~D.dil)&(D.close>=1000)).fillna(False)
X=D[D1].copy()
def S(s,h=20):
    r=s[f"n{h}"].dropna().values
    if len(r)<15: return None
    pf=r[r>0].sum()/abs(r[r<=0].sum()) if (r<=0).any() else 99
    return len(r),r.mean(),np.median(r),(r>0).mean()*100,pf,np.percentile(r,5),r.min()
print("## 1) 기존 D1 에 조건 추가 — 검증기간 기준\n")
print("| 추가 조건 | 건수 | 학습 | **검증** | 중앙값 | 승률 | PF | 하위5% | 최악 |\n|---|---|---|---|---|---|---|---|---|")
for nm,m in [("없음(현행 D1)",pd.Series(True,index=X.index)),
             ("기관20일 ≥ 0%",X.ow20>=0),("기관20일 ≥ 1%",X.ow20>=1),
             ("기관5일 ≥ 0%",X.ow5>=0),("외인60일 ≥ 2%",X.fw60>=2),
             ("변동성 ≤ 5%",X.vol20<=5),("거래대금 ≥ 10억",X.amt20>=10),
             ("기관20일≥0 + 거래대금≥10억",(X.ow20>=0)&(X.amt20>=10))]:
    s=X[m.fillna(False)]
    a=S(s[s.y<=2022]); b=S(s[s.y>=2023])
    if not b: print(f"| {nm} | {len(s)} | 표본부족 | | | | | | |"); continue
    print(f"| {nm} | {len(s)} | {a[1] if a else float('nan'):+.2f}% | **{b[1]:+.2f}%** | {b[2]:+.2f}% | {b[3]:.0f}% | {b[4]:.2f} | {b[5]:.1f}% | {b[6]:.0f}% |")

print("\n## 2) 코스닥 조정매집 (P2 코스닥판) 탐색 — 학습에서만 선별\n")
SAFE=((D.close>=1000)&(~D.dil)&(D.amt20>=5)&(D.ret500<=100)).fillna(False)
Y=D[SAFE].copy()
OPT={"거래량침체r16<30":Y.r16<30,"거래량침체r16<50":Y.r16<50,"급증rw1≥200":Y.rw1>=200,
     "외인5일≥2":Y.fw5>=2,"외인5일≥5":Y.fw5>=5,"기관20일≥0":Y.ow20>=0,
     "3일수익≤-5":Y.ret3<=-5,"10일수익≤0":Y.ret10<=0,"코스닥20일선아래":~Y.q20,
     "공매도감소":Y.srd==True,"공매도≤1":Y.sr20<=1,"변동성≤4":Y.vol20<=4}
res=[]
for k in (4,5,6):
    for c in itertools.combinations(OPT,k):
        m=pd.Series(True,index=Y.index)
        for n in c: m&=OPT[n].fillna(False)
        s=Y[m]
        if not (100<=len(s)<=1500): continue
        a=s[s.y<=2022]; b=s[s.y>=2023]
        for h in (10,20):
            ra=a[f"n{h}"].dropna().values; rb=b[f"n{h}"].dropna().values
            if len(ra)<50 or len(rb)<30: continue
            if (ra>0).mean()<0.65: continue
            pf=rb[rb>0].sum()/abs(rb[rb<=0].sum()) if (rb<=0).any() else 99
            res.append((" + ".join(c),h,len(s),len(ra),(ra>0).mean()*100,ra.mean(),
                        len(rb),(rb>0).mean()*100,rb.mean(),np.median(rb),pf,np.percentile(rb,5)))
print(f"학습 승률 65%↑ 조합 {len(res)}개")
if res:
    res.sort(key=lambda r:-r[4])
    print("\n| 조합 | 보유 | 학습건수 | **학습승률** | 검증건수 | **검증승률** | 검증평균 | 중앙값 | PF | 하위5% |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in res[:10]:
        print(f"| {r[0]} | {r[1]}일 | {r[3]} | **{r[4]:.0f}%** | {r[6]} | **{r[7]:.0f}%** | {r[8]:+.2f}% | {r[9]:+.2f}% | {r[10]:.2f} | {r[11]:.1f}% |")
    print(f"\n검증도 승률 60%↑ 유지: {len([r for r in res if r[7]>=60])}/{len(res)}개")
