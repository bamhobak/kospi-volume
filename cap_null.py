# -*- coding: utf-8 -*-
"""학습 성적이 검증을 예측하는가 — 귀무가설 검정 + 기존 규칙과의 중복"""
import io,sys,csv,itertools,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
IND={}
for r in csv.DictReader(open("data/industry.csv",encoding="utf-8-sig")):
    k=list(r.values()); IND[k[0]]=k[-1]
def prep(path,amtmin):
    D=pd.read_pickle(path); D["up"]=D.ticker.map(IND)
    d=D[D.up.notna()].dropna(subset=["ret60"]); g=d.groupby(["date","up"]).ret60
    m=g.median(); c=g.size(); m=m[c>=5]
    D["u"]=pd.MultiIndex.from_arrays([D.date,D.up]).map(m)
    return D[((D.close>=1000)&(~D.dil)&(D.amt20>=amtmin)&D.PBR.notna()).fillna(False)].copy()
def run(D,label,amtmin):
    OPT={"PBR≤0.5":D.PBR<=0.5,"PBR≤1":D.PBR<=1,"시총≤1000억":D.marcap<=1000,"시총≤3000억":D.marcap<=3000,
         "회전율≥0.5":D.회전율>=0.5,"회전율≥1":D.회전율>=1,
         "외인60일≥1":D.fw60>=1,"기관20일≥0":D.ow20>=0,"공매도감소":D.srd==True,
         "20일수익≤-10":D.ret20<=-10,"20일수익≤0":D.ret20<=0,"20일수익≥0":D.ret20>=0,
         "업종60일≤-10":D.u<=-10,"거래량급증su1≥2":D.su1>=2,"신고가-20이내":D.fromhi>=-20,
         "부채비율≤100":D.부채비율<=100,"ROE≥0":D.ROE>=0,"자사주≥1":D.자사주>=1}
    allr=[]
    for k in (3,4,5):
        for c in itertools.combinations(OPT,k):
            m=pd.Series(True,index=D.index)
            for n in c: m&=OPT[n].fillna(False)
            s=D[m]
            if not (150<=len(s)<=4000): continue
            a=s[s.y<=2022]; b=s[s.y>=2023]
            for h in (20,40):
                ra=a[f"n{h}"].dropna().values; rb=b[f"n{h}"].dropna().values
                if len(ra)<80 or len(rb)<40: continue
                allr.append((" + ".join(c),h,(ra>0).mean()*100,ra.mean(),(rb>0).mean()*100,rb.mean()))
    A=pd.DataFrame(allr,columns=["c","h","isw","isr","osw","osr"])
    print(f"\n## {label} — 전체 조합 {len(A):,}개\n")
    hi=A[A.isw>=62]; lo=A[A.isw<62]
    print(f"| 구분 | 개수 | 검증 승률 60%↑ 비율 | 검증 평균수익 |\n|---|---|---|---|")
    print(f"| 학습 승률 62%↑ (선별됨) | {len(hi):,} | **{(hi.osw>=60).mean()*100:.1f}%** | {hi.osr.mean():+.2f}% |")
    print(f"| 학습 승률 62% 미만 | {len(lo):,} | **{(lo.osw>=60).mean()*100:.1f}%** | {lo.osr.mean():+.2f}% |")
    print(f"| 전체 | {len(A):,} | {(A.osw>=60).mean()*100:.1f}% | {A.osr.mean():+.2f}% |")
    cor=A[["isw","osw"]].corr().iloc[0,1]; cor2=A[["isr","osr"]].corr().iloc[0,1]
    print(f"\n학습↔검증 상관: 승률 **{cor:+.3f}** · 수익 **{cor2:+.3f}**")
    print("→ " + ("학습 성적이 검증을 예측한다" if cor>0.15 else "**학습 성적에 예측력이 없다 — 선별이 무의미**"))
    return A
run(prep("data/kp_cap.pkl",10),"코스피",10)
run(prep("data/kq_cap.pkl",5),"코스닥",5)
