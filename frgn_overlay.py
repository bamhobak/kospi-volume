# -*- coding: utf-8 -*-
"""외인 지분율 낙폭(1년 평균 대비 최근 한 달)을 [폭락반등](P3)·[낙폭과대](D1)에 얹는다.
규칙 단위 + 계좌 12시드 짝비교(전체/학습/검증/붐제외) + 연도별.
"""
import io, sys, sqlite3, warnings; warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns); sys.stdout = real
KP, KQ, RULES = ns["KP"], ns["KQ"], ns["RULES"]
adates = sorted(set(KP.date)|set(KQ.date)); ADI = {d:i for i,d in enumerate(adates)}
rel = (BASE/"rules_relation.py").read_text(encoding="utf-8")
exec(rel[rel.index("def build(R):"):rel.index("S = build(RULES)")], globals())
exec(rel[rel.index("def sim(S, ds, seed):"):rel.index("ds = [d for d in adates")].replace(
     "return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid)", "return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid, curve=Cv)"), globals())
# 외인 지분율 붙이기
F=[]
for db in ("kospi.db","kosdaq.db"):
    c=sqlite3.connect(f"file:{BASE}/data/{db}?mode=ro",uri=True)
    F.append(pd.read_sql("select date,ticker,foreign_ratio fr from daily where date>='20170101' and foreign_ratio is not null",c)); c.close()
F=pd.concat(F).drop_duplicates(["ticker","date"]).sort_values(["ticker","date"])
gF=F.groupby("ticker",sort=False)
F["fr250"]=gF.fr.transform(lambda s: s.rolling(250,min_periods=200).mean())
F["fr20"]=gF.fr.transform(lambda s: s.rolling(20).mean())
F["frr"]=F.fr20/F.fr250.replace(0,np.nan)
for K in (KP,KQ):
    n0=len(K); M=K.merge(F[["ticker","date","fr","fr250","frr"]],on=["ticker","date"],how="left"); assert len(M)==n0
    for c in ("fr","fr250","frr"): K[c]=M[c].values
del F
print(f"지분율 결측률 — 코스피 {KP.frr.isna().mean():.1%} · 코스닥 {KQ.frr.isna().mean():.1%}")
OV = {
 "지분율비 < 0.5 (반토막)":      lambda K: K.frr<0.5,
 "지분율비 < 0.7":              lambda K: K.frr<0.7,
 "지분율비 < 0.9":              lambda K: K.frr<0.9,
 "지분율비 ≥ 0.9 (안 빠짐)":     lambda K: K.frr>=0.9,
 "지분율비 ≥ 1.0":              lambda K: K.frr>=1.0,
 "1년 평균 지분율 ≥ 5%":         lambda K: K.fr250>=5,
 "1년 평균 지분율 < 2%":         lambda K: K.fr250<2,
}
def boot(v,k,seed=777,n=2000):
    if len(v)<25: return None
    rng=np.random.default_rng(seed); d=pd.DataFrame({"r":np.asarray(v),"ym":np.asarray(k)})
    ms=d.ym.unique(); by={m:d[d.ym==m].r.to_numpy() for m in ms}
    return np.percentile([np.concatenate([by[x] for x in rng.choice(ms,len(ms),replace=True)]).mean() for _ in range(n)],[2.5,97.5])
def fci(c): return f"[{c[0]:+.1f},{c[1]:+.1f}]" if c is not None else "-"
def stats(K,hold,cond):
    col=f"n{hold}"
    if col not in K.columns:
        gg=K.groupby("ticker",sort=False); K[col]=(gg.close.shift(-hold)/K.buy-1)*100-K.cost
    X=K[cond.fillna(False)].dropna(subset=[col]).sort_values("date"); keep,last=[],{}
    for r in X.itertuples():
        i=ADI[r.date]
        if last.get(r.ticker,-10**9)>=i: continue
        last[r.ticker]=i+hold; keep.append(r.Index)
    Y=X.loc[keep]; r=Y[col]; ym=Y.date.str[:6]; IS=Y.date<"20230101"; NB=Y.date<"20250101"
    return dict(n=len(Y), avg=r.mean(), med=r.median(), win=(r>0).mean()*100,
                ci=boot(r[IS].values,ym[IS].values) if IS.sum()>=25 else None,
                cn=boot(r[NB].values,ym[NB].values) if NB.sum()>=25 else None,
                os=r[~IS].mean() if (~IS).sum() else np.nan, Y=Y)
PER=[("전체","20180101","20991231"),("학습","20180101","20221231"),("검증","20230101","20991231"),("붐제외","20180101","20241231")]
SEEDS=12; ds_all=[d for d in adates if d>="20180101"]; yrs=np.array([d[:4] for d in ds_all])
def run(R,d0,d1): S=build(R); ds=[d for d in adates if d0<=d<=d1]; return [sim(S,ds,k) for k in range(SEEDS)]
def yr_ret(runs):
    out={}
    for y in sorted(set(yrs)):
        idx=np.where(yrs==y)[0]; i0=max(idx[0]-1,0); i1=idx[-1]
        out[y]=np.array([(r["curve"].to_numpy()[i1]/r["curve"].to_numpy()[i0]-1)*100 for r in runs])
    return out
B={p[0]: run(RULES,p[1],p[2]) for p in PER}; BY=yr_ret(B["전체"])
print("기준 9규칙: " + " · ".join(f"{p[0]} {np.median([r['nav'] for r in B[p[0]]]):.2f}배" for p in PER))
for rid,nm in (("P3","폭락반등"),("D1","낙폭과대")):
    K,hold,stop,pct,mx,cond = RULES[rid]
    b=stats(K,hold,cond)
    print(f"\n━━━ [{nm}] 원본 {b['n']}건 평균 {b['avg']:+.2f} 중앙 {b['med']:+.1f} 승률 {b['win']:.0f}% 학습CI {fci(b['ci'])} 붐제외CI {fci(b['cn'])} 검증 {b['os']:+.2f} ━━━")
    cov=b["Y"].frr.notna().mean(); print(f"  (원본 신호 중 지분율 값이 있는 비율 {cov:.0%})")
    print(f"  {'조건':<24}{'n':>6}{'평균':>8}{'중앙':>7}{'승률':>6}{'검증':>8}  {'학습CI':<14}{'붐제외CI':<14} 계좌 전체/학습/검증/붐제외")
    for on,of in OV.items():
        c2=cond&of(K); s=stats(K,hold,c2)
        if s["n"]<25: print(f"  {on:<24}{s['n']:>6} (부족)"); continue
        d=s["avg"]-b["avg"]; cells=""
        if d>0.3:
            R2={**RULES, rid:(K,hold,stop,pct,mx,c2)}
            res={p[0]: run(R2,p[1],p[2]) for p in PER}
            cells=" "+" ".join(f"{np.median([r['nav'] for r in res[p[0]]]):.2f}({np.mean([a['nav']>bb['nav'] for a,bb in zip(res[p[0]],B[p[0]])])*100:.0f}%)" for p in PER)
            Y=yr_ret(res["전체"]); won=lost=0
            for y in sorted(Y):
                dm=np.median(Y[y])-np.median(BY[y])
                won+=dm>0.05; lost+=dm<-0.05
            cells+=f" 이김{won}짐{lost}"
        else: cells=" (계좌 생략)"
        print(f"  {on:<24}{s['n']:>6}{s['avg']:>+8.2f}{s['med']:>+7.1f}{s['win']:>5.0f}%{s['os']:>+8.2f}  {fci(s['ci']):<14}{fci(s['cn']):<14}{cells}  {'▲' if d>0.5 else ('▼' if d<-0.5 else '=')}")
