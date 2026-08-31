# -*- coding: utf-8 -*-
"""저PBR 낙폭과대 후보 정밀 검증 — D1 과 겹치는가, 새 구간을 메우는가"""
import io,sys,csv,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
IND={}
for r in csv.DictReader(open("data/industry.csv",encoding="utf-8-sig")):
    k=list(r.values()); IND[k[0]]=k[-1]
D=pd.read_pickle("data/kq_cap.pkl"); D["up"]=D.ticker.map(IND)
d=D[D.up.notna()].dropna(subset=["ret60"]); g=d.groupby(["date","up"]).ret60
m=g.median(); c=g.size(); m=m[c>=5]
D["u"]=pd.MultiIndex.from_arrays([D.date,D.up]).map(m)
SAFE=((D.close>=1000)&(~D.dil)&(D.amt20>=5)).fillna(False)
CAND=(SAFE&(D.PBR<=0.5)&(D.srd==True)&(D.ret20<=-10)&(D.u<=-10)&(D.su1>=2)).fillna(False)
D1=((D.ret20<=-20)&(D.su1>=2)&(D.fw60>=1)&(D.amt20>=2)&(~D.k60)&(D.srd==True)&(~D.dil)
    &(D.close>=1000)&(D.ow20>=0)&D.u.notna()&(D.u<=-20)&(D.부채비율.fillna(0)<=200)).fillna(False)
X=D[CAND].copy(); Y=D[D1]
sx=set(zip(X.date,X.ticker)); sy=set(zip(Y.date,Y.ticker))
print(f"## 후보 {len(X)}건 vs D1 {len(Y)}건\n")
print(f"- 겹치는 신호: **{len(sx&sy)}건** (후보의 {len(sx&sy)/len(sx)*100:.0f}%, D1의 {len(sx&sy)/len(sy)*100:.0f}%)")
def S(r):
    r=np.asarray(r); pf=r[r>0].sum()/abs(r[r<=0].sum()) if (r<=0).any() else 99
    return len(r),r.mean(),np.median(r),(r>0).mean()*100,pf,r.min()
rng=np.random.default_rng(5)
X["ym"]=X.date.str[:6]
print("\n## 후보 성적\n")
print("| 구간 | 보유 | 건수 | 평균 | 중앙값 | 승률 | PF | 최악 |\n|---|---|---|---|---|---|---|---|")
for h in (20,40):
    for t,s in [("학습",X[X.y<=2022]),("검증",X[X.y>=2023])]:
        n,mn,md,w,pf,mi=S(s[f"n{h}"].dropna())
        print(f"| {t} | {h}일 | {n} | **{mn:+.2f}%** | {md:+.2f}% | {w:.0f}% | {pf:.2f} | {mi:.0f}% |")
V=X[X.y>=2023]
mo=[list(x.dropna()) for _,x in V.groupby("ym").n40]; mo=[x for x in mo if x]
bs=np.array([np.mean([v for i in rng.integers(0,len(mo),len(mo)) for v in mo[i]]) for _ in range(2000)])
print(f"\n검증 40일 월단위 95% 신뢰구간: **{np.percentile(bs,2.5):+.1f} ~ {np.percentile(bs,97.5):+.1f}%** · 신호 난 달 {V.ym.nunique()}/44")
print("\n## D1 과 겹치지 않는 신호만 (새로 얻는 부분)\n")
only=X[~X.set_index(["date","ticker"]).index.isin(sy)]
for t,s in [("학습",only[only.y<=2022]),("검증",only[only.y>=2023])]:
    n,mn,md,w,pf,mi=S(s.n40.dropna())
    print(f"- {t}: {n}건 평균 **{mn:+.2f}%** 중앙 {md:+.2f}% 승률 {w:.0f}% PF {pf:.2f}")
print("\n## 시장 국면 (D1 은 코스피 60일선 아래에서만, 후보는 제한 없음)\n")
print("| 국면 | 후보 건수 | 검증 평균 |\n|---|---|---|")
for lab,mm in [("코스피 60일선 위",X.k60),("아래",~X.k60)]:
    s=X[mm]; b=s[s.y>=2023].n40.dropna()
    print(f"| {lab} | {len(s)} | {b.mean() if len(b) else float('nan'):+.2f}% ({len(b)}건) |")
print("\n연도별:", " / ".join(f"{y} {gg.n40.mean():+.1f}%({len(gg)}건)" for y,gg in X.groupby("y")))
