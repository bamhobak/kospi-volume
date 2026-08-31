# -*- coding: utf-8 -*-
"""고빈도 규칙 탐색 — 승률은 낮아도 신호가 많은 조건.
   목표: 검증 300건 이상(월 7건+), 학습 승률 52%+ (기준선 41~43%)
   선별은 학습에서만. 두 보유기간에서 모두 살아남는지 확인.
"""
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
    return D[((D.close>=1000)&(~D.dil)&(D.amt20>=amtmin)).fillna(False)].copy()
def search(D,label):
    B=D
    OPT={
     "PBR≤0.5":B.PBR<=0.5,"PBR≤1":B.PBR<=1,
     "시총≤1000억":B.marcap<=1000,"시총≤3000억":B.marcap<=3000,
     "업종60일≤-10":B.u<=-10,"업종60일≤-20":B.u<=-20,
     "20일수익≤-10":B.ret20<=-10,"20일수익≤0":B.ret20<=0,
     "60일수익≤-20":B.ret60<=-20,
     "외인60일≥1":B.fw60>=1,"기관20일≥0":B.ow20>=0,"공매도감소":B.srd==True,
     "공매도비중≤1":B.sr20<=1,"부채비율≤100":B.부채비율<=100,"ROE≥0":B.ROE>=0,
     "회전율≥0.5":B.회전율>=0.5,"20일선이격≤-10":B.dma20<=-10,
     "고점대비≤-30":B.fromhi<=-30,"변동성≤3":B.vol20<=3,
    }
    res=[]
    for k in (2,3,4):
        for c in itertools.combinations(OPT,k):
            m=pd.Series(True,index=B.index)
            for n in c: m&=OPT[n].fillna(False)
            s=B[m]
            if len(s)<2000: continue
            a=s[s.y<=2022]; b=s[s.y>=2023]
            for h in (20,40):
                ra=a[f"n{h}"].dropna().values; rb=b[f"n{h}"].dropna().values
                if len(ra)<800 or len(rb)<300: continue
                if (ra>0).mean()<0.52: continue
                pf=rb[rb>0].sum()/abs(rb[rb<=0].sum())
                res.append((" + ".join(c),h,len(s),len(ra),(ra>0).mean()*100,ra.mean(),
                            len(rb),(rb>0).mean()*100,rb.mean(),np.median(rb),pf))
    print(f"\n{'='*6} {label} — 학습 승률 52%↑ · 검증 300건↑ 조합 {len(res)}개 {'='*6}\n")
    if not res: print("해당 없음"); return []
    res.sort(key=lambda r:-r[4])
    print("| 조합 | 보유 | 전체 | 학습승률 | 학습평균 | 검증건수 | **검증승률** | **검증평균** | 중앙값 | PF |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in res[:14]:
        print(f"| {r[0]} | {r[1]}일 | {r[2]:,} | {r[4]:.0f}% | {r[5]:+.1f}% | {r[6]:,} | **{r[7]:.0f}%** | **{r[8]:+.2f}%** | {r[9]:+.2f}% | {r[10]:.2f} |")
    ok=[r for r in res if r[7]>=52 and r[8]>0]
    print(f"\n검증에서도 승률 52%↑ & 수익 (+): **{len(ok)}/{len(res)}개**")
    return res
K=search(prep("data/kp_cap.pkl",10),"코스피")
Q=search(prep("data/kq_cap.pkl",5),"코스닥")
import pickle; pickle.dump({"K":K,"Q":Q},open("data/wide_res.pkl","wb"))
