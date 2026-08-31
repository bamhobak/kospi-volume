# -*- coding: utf-8 -*-
"""저PBR·소형주 축으로 새 규칙 탐색 — 학습에서만 선별, 안정성 기준"""
import io,sys,csv,itertools,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
IND={}
for r in csv.DictReader(open("data/industry.csv",encoding="utf-8-sig")):
    k=list(r.values()); IND[k[0]]=k[-1]
def prep(path,amtmin):
    D=pd.read_pickle(path)
    D["up"]=D.ticker.map(IND)
    d=D[D.up.notna()].dropna(subset=["ret60"]); g=d.groupby(["date","up"]).ret60
    m=g.median(); c=g.size(); m=m[c>=5]
    D["u"]=pd.MultiIndex.from_arrays([D.date,D.up]).map(m)
    return D[((D.close>=1000)&(~D.dil)&(D.amt20>=amtmin)&D.PBR.notna()).fillna(False)].copy()
def search(D,label,amtmin):
    print(f"\n{'='*8} {label} {'='*8}")
    OPT={"PBR≤0.5":D.PBR<=0.5,"PBR≤1":D.PBR<=1,"시총≤1000억":D.marcap<=1000,"시총≤3000억":D.marcap<=3000,
         "회전율≥0.5":D.회전율>=0.5,"회전율≥1":D.회전율>=1,
         "외인60일≥1":D.fw60>=1,"기관20일≥0":D.ow20>=0,"공매도감소":D.srd==True,
         "20일수익≤-10":D.ret20<=-10,"20일수익≤0":D.ret20<=0,"20일수익≥0":D.ret20>=0,
         "업종60일≤-10":D.u<=-10,"거래량급증su1≥2":D.su1>=2,"신고가-20이내":D.fromhi>=-20,
         "부채비율≤100":D.부채비율<=100,"ROE≥0":D.ROE>=0,"자사주≥1":D.자사주>=1}
    res=[]
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
                if (ra>0).mean()<0.62: continue
                pf=rb[rb>0].sum()/abs(rb[rb<=0].sum()) if (rb<=0).any() else 99
                res.append((" + ".join(c),h,len(s),len(ra),(ra>0).mean()*100,ra.mean(),
                            len(rb),(rb>0).mean()*100,rb.mean(),np.median(rb),pf))
    print(f"학습 승률 62%↑ 조합 {len(res)}개")
    if not res: return
    res.sort(key=lambda r:-r[4])
    print("\n| 조합 | 보유 | 학습건수 | **학습승률** | 학습평균 | 검증건수 | **검증승률** | 검증평균 | 중앙값 | PF |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in res[:12]:
        print(f"| {r[0]} | {r[1]}일 | {r[3]} | **{r[4]:.0f}%** | {r[5]:+.1f}% | {r[6]} | **{r[7]:.0f}%** | {r[8]:+.2f}% | {r[9]:+.2f}% | {r[10]:.2f} |")
    ok=[r for r in res if r[7]>=60]
    print(f"\n검증에서도 승률 60%↑ 유지: **{len(ok)}/{len(res)}개**")
search(prep("data/kp_cap.pkl",10),"코스피",10)
search(prep("data/kq_cap.pkl",5),"코스닥",5)
