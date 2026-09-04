# -*- coding: utf-8 -*-
"""조인 셀이 기존 9규칙과 얼마나 겹치나 — 규칙별 겹침 · 겹치는 신호를 뺀 나머지의 성적 · 계좌."""
import io, sys, sqlite3, warnings; warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE=Path(__file__).parent
src=(BASE/"portfolio.py").read_text(encoding="utf-8"); ns={"__file__": str(BASE/"portfolio.py")}
real=sys.stdout; sys.stdout=io.TextIOWrapper(io.BytesIO(),encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0],"portfolio.py","exec"), ns); sys.stdout=real
KP,KQ,RULES,base=ns["KP"],ns["KQ"],ns["RULES"],ns["base"]
adates=sorted(set(KP.date)|set(KQ.date)); ADI={d:i for i,d in enumerate(adates)}
rel=(BASE/"rules_relation.py").read_text(encoding="utf-8")
exec(rel[rel.index("def build(R):"):rel.index("S = build(RULES)")], globals())
exec(rel[rel.index("def sim(S, ds, seed):"):rel.index("ds = [d for d in adates")].replace(
     "return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid)","return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid, curve=Cv)"), globals())
NAME={"P7":"외인 매집","P1":"조용한 신고가","P4":"업종붕괴 이탈","P6":"깊은 이격","P3":"폭락반등","P2":"조정매집","D1":"낙폭과대","D2":"저PBR 낙폭","P5":"자사주 낙폭"}
c=sqlite3.connect(f"file:{BASE}/data/toss.db?mode=ro",uri=True)
P=pd.read_sql("select date,ticker,arb_net from program",c)
S=pd.read_sql("select date,ticker,vol_rate from short where vol_rate is not null",c); c.close()
X=P.merge(S,on=["date","ticker"],how="outer").sort_values(["ticker","date"]).merge(
    KP[["date","ticker","volume"]],on=["date","ticker"],how="left")
gX=X.groupby("ticker",sort=False)
X["pa20"]=gX.arb_net.transform(lambda s: s.rolling(20,min_periods=15).sum())/gX.volume.transform(lambda s: s.rolling(20,min_periods=15).sum()).replace(0,np.nan)*100
X["sr"]=gX.vol_rate.transform(lambda s: s.rolling(20,min_periods=15).mean())/gX.vol_rate.transform(lambda s: s.rolling(250,min_periods=200).mean()).replace(0,np.nan)
n0=len(KP); T=KP.merge(X[["date","ticker","pa20","sr"]],on=["ticker","date"],how="left"); assert len(T)==n0
KP["pa20"]=T.pa20.values; KP["sr2"]=T.sr.values; del T,X,P,S
KP["di"]=KP.date.map(ADI)
S0=build(RULES); S0=S0.assign(di=S0.date.map(ADI))
def dedup(cond,hold=20):
    Z=KP[cond.fillna(False)].sort_values("di"); keep,last=[],{}
    for r in Z.itertuples():
        if last.get(r.ticker,-10**9)>=r.di: continue
        last[r.ticker]=r.di+hold; keep.append(r.Index)
    return KP.loc[keep]
VAR={"원안 공매도<0.7·차익<-0.3": (KP.sr2<0.7)&(KP.pa20<-0.3),
     "조임1 공매도<0.5·차익<-0.5": (KP.sr2<0.5)&(KP.pa20<-0.5),
     "조임2 공매도<0.5·차익<-1.0": (KP.sr2<0.5)&(KP.pa20<-1.0),
     "조임3 공매도<0.4·차익<-1.0": (KP.sr2<0.4)&(KP.pa20<-1.0)}
print(f"{'후보':<26}{'신호':>7}{'겹침':>7}   규칙별 겹침(상위 4)")
OVSET={}
for nm,cond in VAR.items():
    Z=dedup(base(KP,30)&cond)
    m=Z[["ticker","di"]].merge(S0[["ticker","di","rid"]],on="ticker",suffixes=("","_e"))
    m=m[(m.di_e-m.di).abs()<=5]
    hit=set(zip(m.ticker,m.di)); OVSET[nm]=hit
    per=m.groupby("rid").apply(lambda d: len(set(zip(d.ticker,d.di)))).sort_values(ascending=False)
    top=" · ".join(f"[{NAME[r]}] {v/max(len(Z),1)*100:.0f}%" for r,v in per.head(4).items())
    print(f"{nm:<26}{len(Z):>7,}{len(hit)/max(len(Z),1)*100:>6.0f}%   {top}")
print()
# 겹치는 신호를 뺀 나머지만 남기면?
def stats(Z,hold=20):
    col=f"n{hold}"
    if col not in KP.columns:
        gg=KP.groupby("ticker",sort=False); KP[col]=(gg.close.shift(-hold)/KP.buy-1)*100-KP.cost
    Y=Z.dropna(subset=[col]); r=Y[col]
    return len(Y), r.mean(), r.median(), (r>0).mean()*100
print("■ 겹치는 신호를 빼면 (20일 · 코스피)")
print(f"  {'후보':<26}{'전체 n/평균/중앙/승률':<34}{'겹침 제외 후 n/평균/중앙/승률'}")
for nm,cond in VAR.items():
    Z=dedup(base(KP,30)&cond); hit=OVSET[nm]
    keep=Z[[ (t,d) not in hit for t,d in zip(Z.ticker,Z.di)]]
    a=stats(Z); b=stats(keep)
    print(f"  {nm:<26}{a[0]:>5} {a[1]:>+6.2f} {a[2]:>+5.1f} {a[3]:>3.0f}%          {b[0]:>5} {b[1]:>+6.2f} {b[2]:>+5.1f} {b[3]:>3.0f}%")
print()
PER=[("전체","20180101","20991231"),("검증","20230101","20991231"),("붐제외","20180101","20241231")]
SEEDS=12
def run(R,d0,d1): S2=build(R); ds=[d for d in adates if d0<=d<=d1]; return [sim(S2,ds,k) for k in range(SEEDS)]
B={p[0]: run(RULES,p[1],p[2]) for p in PER}
print("■ 계좌 (10번째 규칙 · 코스피 20일 4%·최대4)")
print("기준 9규칙: " + " · ".join(f"{p[0]} {np.median([r['nav'] for r in B[p[0]]]):.2f}배" for p in PER) + f" · 낙폭 {np.median([r['mdd'] for r in B['전체']]):.1f}%")
def scaled(R,k): return {r:(K2,h,s,p*k,m,c2) for r,(K2,h,s,p,m,c2) in R.items()}
for nm,cond in VAR.items():
    R={**RULES,"N":(KP,20,None,4,4, base(KP,30)&cond)}
    res={p[0]: run(R,p[1],p[2]) for p in PER}
    cells=" · ".join(f"{p[0]} {np.median([r['nav'] for r in res[p[0]]]):.2f}({np.mean([a['nav']>b['nav'] for a,b in zip(res[p[0]],B[p[0]])])*100:.0f}%)" for p in PER)
    line=""
    for k in (0.5,1.5):
        bb=[r["nav"] for r in run(scaled(RULES,k),"20180101","20991231")]; vv=[r["nav"] for r in run(scaled(R,k),"20180101","20991231")]
        line+=f" ×{k} {np.mean([a>c for a,c in zip(vv,bb)])*100:.0f}%"
    print(f"  {nm:<26}{cells} · 낙폭 {np.median([r['mdd'] for r in res['전체']]):.1f}% · 착시{line}")
