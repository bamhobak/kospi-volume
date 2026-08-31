# -*- coding: utf-8 -*-
"""상승장 조합: 학습 성적이 검증을 예측하는가 + 최선 후보 정밀 평가"""
import io,sys,itertools,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
K=pd.read_pickle("data/kp_hz2.pkl")
B=K[((K.k60)&(K.k20)&K.ok).fillna(False)]      # 상승추세 (후보가 가장 좋았던 국면)
OPT={"신고가-5이내":B.fromhi>=-5,"신고가-10이내":B.fromhi>=-10,
     "거래량침체r16<80":B.r16<80,"단기잠잠rw1≤120":B.rw1<=120,
     "외인5일≥3":B.fw5>=3,"외인60일≥1":B.fw60>=1,"기관20일≥0":B.ow20>=0,
     "공매도감소":B.srd==True,"공매도비중≤0.5":B.sr20<=0.5,
     "변동성≤2":B.vol20<=2,"변동성≤3":B.vol20<=3,
     "20일수익≤5":B.ret20<=5,"PBR≤1":B.PBR<=1,"시총≤3000억":B.marcap<=3000,
     "회전율≥0.5":B.회전율>=0.5,"업종60일≥0":B.u>=0}
rows=[]
for k in (2,3,4):
    for c in itertools.combinations(OPT,k):
        m=pd.Series(True,index=B.index)
        for n in c: m&=OPT[n].fillna(False)
        s=B[m]
        if len(s)<1500: continue
        a=s[s.y<=2022]; b=s[s.y>=2023]
        for h in (5,10,20,40):
            ra=a[f"n{h}"].dropna().values; rb=b[f"n{h}"].dropna().values
            if len(ra)<600 or len(rb)<250: continue
            rows.append((" + ".join(c),h,(ra>0).mean()*100,ra.mean(),(rb>0).mean()*100,rb.mean(),len(s)))
A=pd.DataFrame(rows,columns=["c","h","isw","isr","osw","osr","n"])
print(f"## 코스피 상승추세 — 전체 조합 {len(A):,}개\n")
hi=A[A.isw>=55]; lo=A[A.isw<55]
print("| 구분 | 개수 | 검증 승률 55%↑ | 검증 평균수익 |\n|---|---|---|---|")
print(f"| 학습 승률 55%↑ (선별) | {len(hi):,} | **{(hi.osw>=55).mean()*100:.1f}%** | {hi.osr.mean():+.2f}% |")
print(f"| 학습 승률 55% 미만 | {len(lo):,} | **{(lo.osw>=55).mean()*100:.1f}%** | {lo.osr.mean():+.2f}% |")
print(f"| 전체 | {len(A):,} | {(A.osw>=55).mean()*100:.1f}% | {A.osr.mean():+.2f}% |")
print(f"\n학습↔검증 상관: 승률 **{A[['isw','osw']].corr().iloc[0,1]:+.3f}** · 수익 **{A[['isr','osr']].corr().iloc[0,1]:+.3f}**")
print("\n## 최선 후보 정밀 평가 — 신고가-5 + 공매도≤0.5 + 변동성≤2 + PBR≤1\n")
M=((B.fromhi>=-5)&(B.sr20<=0.5)&(B.vol20<=2)&(B.PBR<=1)).fillna(False)
X=B[M].copy(); X["ym"]=X.date.str[:6]
rng=np.random.default_rng(31)
print("| 보유 | 학습승률 | 학습평균 | 검증건수 | **검증승률** | **검증평균** | 중앙값 | PF | **월단위 95%** |")
print("|---|---|---|---|---|---|---|---|---|")
for h in (5,10,20,40,60):
    if f"n{h}" not in X.columns: continue
    a=X[X.y<=2022][f"n{h}"].dropna().values; b=X[X.y>=2023]
    r=b[f"n{h}"].dropna().values
    if len(r)<50: continue
    pf=r[r>0].sum()/abs(r[r<=0].sum()) if (r<=0).any() else 99
    mo=[list(x.dropna()) for _,x in b.groupby("ym")[f"n{h}"]]; mo=[x for x in mo if x]
    bs=np.array([np.mean([v for i in rng.integers(0,len(mo),len(mo)) for v in mo[i]]) for _ in range(1500)])
    lo_,hi_=np.percentile(bs,2.5),np.percentile(bs,97.5)
    mk="**" if lo_>0 else ""
    print(f"| {h}일 | {(a>0).mean()*100:.0f}% | {a.mean():+.2f}% | {len(r):,} | {(r>0).mean()*100:.0f}% | **{r.mean():+.2f}%** | {np.median(r):+.2f}% | {pf:.2f} | {mk}{lo_:+.2f}~{hi_:+.2f}%{mk} |")
# P1 과 중복
P1=((K.fromhi>=-10)&(K.r16<120)&(K.rw1<=120)&(K.fw5>=3)&(K.fw60>=1)&(K.vol20<=2)&(K.sr20<=0.5)
    &(K.ret20<=5)&(K.amt20>=200)&(~K.dil)).fillna(False)
sx=set(zip(X.date,X.ticker)); sy=set(zip(K[P1].date,K[P1].ticker))
print(f"\nP1 과 신호 중복: {len(sx&sy)}건 (후보의 {len(sx&sy)/len(sx)*100:.1f}%)")
V=X[X.y>=2023]
print(f"검증 {len(V):,}건 · 월평균 {len(V)/44:.1f}건 · 신호 난 달 {V.ym.nunique()}/44")
print("연도별:", " / ".join(f"{y} {gg.n40.mean():+.1f}%({len(gg)}건)" for y,gg in X.groupby("y")))
