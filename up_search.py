# -*- coding: utf-8 -*-
"""상승장·횡보장 고빈도 규칙 탐색 (코스피·코스닥). 학습에서만 선별."""
import io,sys,itertools,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
HZ=[3,5,10,20,40]
def prep(path,amtmin):
    D=pd.read_pickle(path).sort_values(["ticker","date"]).reset_index(drop=True)
    if "n3" not in D.columns:
        dates=sorted(D.date.unique()); DI={x:i for i,x in enumerate(dates)}
        g=D.groupby("ticker",sort=False)
        lp=g.date.transform("max").map(DI); lc=g.close.transform("last"); mp=D.date.map(DI)
        for h in HZ:
            if f"n{h}" in D.columns: continue
            sell=g.close.shift(-h).where(~(mp+h>lp),lc)
            D[f"n{h}"]=(sell/D.buy-1)*100-D.cost
    D["ok"]=((D.close>=1000)&(~D.dil)&(D.amt20>=amtmin)).fillna(False)
    return D
K=prep("data/kp_hz2.pkl",10); Q=prep("data/kq_hz.pkl",5)
Q.to_pickle("data/kq_hz2.pkl")
def regimes(D):
    return {"상승장(60일선 위)":D.k60, "횡보·조정(60↑ 20↓)":D.k60&(~D.k20), "상승추세(60↑ 20↑)":D.k60&D.k20}
for D,label,amtmin in ((K,"코스피",10),(Q,"코스닥",5)):
    print(f"\n{'='*10} {label} {'='*10}")
    for rn,rm in regimes(D).items():
        B=D[(rm&D.ok).fillna(False)]
        a=B[B.y<=2022]
        print(f"\n### {rn} — 학습 {len(a):,}행\n")
        base={h:(a[f"n{h}"].dropna()) for h in HZ}
        print("기준선: "+" · ".join(f"{h}일 승률 {(base[h]>0).mean()*100:.0f}%/{base[h].mean():+.2f}%" for h in HZ))
        OPT={"신고가-5이내":B.fromhi>=-5,"신고가-10이내":B.fromhi>=-10,
             "거래량침체r16<80":B.r16<80,"단기잠잠rw1≤120":B.rw1<=120,"거래량급증rw1≥200":B.rw1>=200,
             "외인5일≥3":B.fw5>=3,"외인60일≥1":B.fw60>=1,"기관20일≥0":B.ow20>=0,
             "공매도감소":B.srd==True,"공매도비중≤0.5":B.sr20<=0.5,
             "변동성≤2":B.vol20<=2,"변동성≤3":B.vol20<=3,
             "20일수익≤5":B.ret20<=5,"20일수익≤-5":B.ret20<=-5,"20일선이격≤-5":B.dma20<=-5,
             "PBR≤1":B.PBR<=1,"시총≤3000억":B.marcap<=3000,"회전율≥0.5":B.회전율>=0.5,
             "업종60일≥0":B.u>=0,"업종60일≤-10":B.u<=-10}
        res=[]
        for k in (2,3,4):
            for c in itertools.combinations(OPT,k):
                m=pd.Series(True,index=B.index)
                for n in c: m&=OPT[n].fillna(False)
                s=B[m]
                if len(s)<1500: continue
                aa=s[s.y<=2022]; bb=s[s.y>=2023]
                for h in HZ:
                    ra=aa[f"n{h}"].dropna().values; rb=bb[f"n{h}"].dropna().values
                    if len(ra)<600 or len(rb)<250: continue
                    if (ra>0).mean()<0.55: continue
                    pf=rb[rb>0].sum()/abs(rb[rb<=0].sum()) if (rb<=0).any() else 99
                    res.append((" + ".join(c),h,len(s),(ra>0).mean()*100,ra.mean(),
                                len(rb),(rb>0).mean()*100,rb.mean(),np.median(rb),pf))
        if not res: print("→ 학습 승률 55%↑ · 검증 250건↑ 조합 **없음**"); continue
        res.sort(key=lambda r:-r[3])
        print(f"\n조합 {len(res)}개 · 상위 8\n")
        print("| 조합 | 보유 | 전체 | 학습승률 | 검증건수 | **검증승률** | **검증평균** | 중앙값 | PF |")
        print("|---|---|---|---|---|---|---|---|---|")
        for r in res[:8]:
            print(f"| {r[0]} | {r[1]}일 | {r[2]:,} | {r[3]:.0f}% | {r[5]:,} | **{r[6]:.0f}%** | **{r[7]:+.2f}%** | {r[8]:+.2f}% | {r[9]:.2f} |")
        ok=[r for r in res if r[6]>=55 and r[7]>0]
        print(f"\n검증도 승률 55%↑ & (+): **{len(ok)}/{len(res)}개**")
