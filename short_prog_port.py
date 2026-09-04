# -*- coding: utf-8 -*-
"""공매도 식음 + 차익 순매도 를 10번째 규칙으로 얹었을 때 계좌가 늘어나는가.
기존 9규칙과 ±5일 겹침, 12시드 짝비교(전체/학습/검증/붐제외), 연도별, 자리 착시.
"""
import io, sys, sqlite3, warnings; warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
src=(BASE/"portfolio.py").read_text(encoding="utf-8"); ns={"__file__": str(BASE/"portfolio.py")}
real=sys.stdout; sys.stdout=io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0],"portfolio.py","exec"), ns); sys.stdout=real
KP,KQ,RULES,base = ns["KP"],ns["KQ"],ns["RULES"],ns["base"]
adates=sorted(set(KP.date)|set(KQ.date)); ADI={d:i for i,d in enumerate(adates)}
rel=(BASE/"rules_relation.py").read_text(encoding="utf-8")
exec(rel[rel.index("def build(R):"):rel.index("S = build(RULES)")], globals())
exec(rel[rel.index("def sim(S, ds, seed):"):rel.index("ds = [d for d in adates")].replace(
     "return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid)","return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid, curve=Cv)"), globals())
c=sqlite3.connect(f"file:{BASE}/data/toss.db?mode=ro",uri=True)
P=pd.read_sql("select date,ticker,arb_net from program",c)
S=pd.read_sql("select date,ticker,vol_rate from short where vol_rate is not null",c); c.close()
X=P.merge(S,on=["date","ticker"],how="outer").sort_values(["ticker","date"])
X=X.merge(KP[["date","ticker","volume"]],on=["date","ticker"],how="left")
gX=X.groupby("ticker",sort=False)
X["pa20"]=gX.arb_net.transform(lambda s: s.rolling(20,min_periods=15).sum())/gX.volume.transform(lambda s: s.rolling(20,min_periods=15).sum()).replace(0,np.nan)*100
X["sr"]=gX.vol_rate.transform(lambda s: s.rolling(20,min_periods=15).mean())/gX.vol_rate.transform(lambda s: s.rolling(250,min_periods=200).mean()).replace(0,np.nan)
n0=len(KP); T=KP.merge(X[["date","ticker","pa20","sr"]],on=["ticker","date"],how="left"); assert len(T)==n0
KP["pa20"]=T.pa20.values; KP["sr2"]=T.sr.values; del T,X,P,S
CAND={
 "공매도<0.7·차익<-0.3 · 20일 4%·4": (KP,20,None,4,4, base(KP,30)&(KP.sr2<0.7)&(KP.pa20<-0.3)),
 "공매도<0.5·차익<-0.5 (조임) · 20일": (KP,20,None,4,4, base(KP,30)&(KP.sr2<0.5)&(KP.pa20<-0.5)),
 "공매도<0.7·차익<-0.3 · 40일": (KP,40,None,4,4, base(KP,30)&(KP.sr2<0.7)&(KP.pa20<-0.3)),
 "공매도<0.7·차익<-0.3·거래대금100억 · 20일": (KP,20,None,4,4, base(KP,100)&(KP.sr2<0.7)&(KP.pa20<-0.3)),
}
S0=build(RULES)
def overlap(cond):
    X2=KP[cond.fillna(False)][["ticker","date"]]; X2["di"]=X2.date.map(ADI)
    ex=S0.assign(di=S0.date.map(ADI))[["ticker","di"]]
    m=X2.merge(ex,on="ticker"); hit=m[(m.di_e-m.di).abs()<=5] if "di_e" in m else m[(m.di_y-m.di_x).abs()<=5]
    return len(hit[["ticker"]].drop_duplicates())/max(X2.ticker.nunique(),1), len(X2)
PER=[("전체","20180101","20991231"),("학습","20180101","20221231"),("검증","20230101","20991231"),("붐제외","20180101","20241231")]
SEEDS=12; ds_all=[d for d in adates if d>="20180101"]; yrs=np.array([d[:4] for d in ds_all])
def run(R,d0,d1,seeds=SEEDS): S2=build(R); ds=[d for d in adates if d0<=d<=d1]; return [sim(S2,ds,k) for k in range(seeds)]
def yr_ret(runs):
    out={}
    for y in sorted(set(yrs)):
        idx=np.where(yrs==y)[0]; i0=max(idx[0]-1,0); i1=idx[-1]
        out[y]=np.array([(r["curve"].to_numpy()[i1]/r["curve"].to_numpy()[i0]-1)*100 for r in runs])
    return out
B={p[0]: run(RULES,p[1],p[2]) for p in PER}; BY=yr_ret(B["전체"])
print("기준 9규칙: " + " · ".join(f"{p[0]} {np.median([r['nav'] for r in B[p[0]]]):.2f}배" for p in PER)
      + f" · 낙폭 {np.median([r['mdd'] for r in B['전체']]):.1f}%\n")
def scaled(R,k): return {r:(K2,h,s,p*k,m,c2) for r,(K2,h,s,p,m,c2) in R.items()}
for nm,tup in CAND.items():
    n=int(tup[5].fillna(False).sum())
    R={**RULES,"N":tup}; res={p[0]: run(R,p[1],p[2]) for p in PER}
    cells=" · ".join(f"{p[0]} {np.median([r['nav'] for r in res[p[0]]]):.2f}({np.mean([a['nav']>b['nav'] for a,b in zip(res[p[0]],B[p[0]])])*100:.0f}%)" for p in PER)
    Y=yr_ret(res["전체"]); won=lost=0; ys=[]
    for y in sorted(Y):
        dm=np.median(Y[y])-np.median(BY[y])
        if abs(dm)<0.05: ys.append(f"{y[2:]}:="); continue
        won+=dm>0; lost+=dm<0; ys.append(f"{y[2:]}:{np.mean(Y[y]>BY[y])*100:.0f}%")
    print(f"━━ {nm} ━━ 원신호 {n:,}행")
    print(f"   {cells} · 낙폭 {np.median([r['mdd'] for r in res['전체']]):.1f}% · 이김{won} 짐{lost}  " + " ".join(ys))
    line="   자리 착시:"
    for k in (0.5,1.5):
        b=[r["nav"] for r in run(scaled(RULES,k),"20180101","20991231")]; v=[r["nav"] for r in run(scaled(R,k),"20180101","20991231")]
        line+=f"  ×{k} {np.median(b):.2f}→{np.median(v):.2f}({np.mean([a>c for a,c in zip(v,b)])*100:.0f}%)"
    print(line)
