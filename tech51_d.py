# -*- coding: utf-8 -*-
"""유튜브 51편 4단계 — 하락장 한정으로 살아남은 반전 기법을 '10번째 규칙' 으로 계좌에 얹으면 늘어나는가.
후보: C08 상승 잉태형+익일 양봉 확인 · G04b 60선 -20% 급락 후 반등 · C12 섬꼴반전 (모두 코스피·dn60 게이트·20일).
기존 9규칙과의 ±5일 겹침, 12시드 짝비교, 연도별 짝비교, 자리 착시(×0.5/×1.5).
"""
import io, sys, warnings; warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns); sys.stdout = real
KP, KQ, RULES, base, dn60 = ns["KP"], ns["KQ"], ns["RULES"], ns["base"], ns["dn60"]
adates = sorted(set(KP.date)|set(KQ.date)); ADI = {d:i for i,d in enumerate(adates)}
rel = (BASE/"rules_relation.py").read_text(encoding="utf-8")
exec(rel[rel.index("def build(R):"):rel.index("S = build(RULES)")], globals())
exec(rel[rel.index("def sim(S, ds, seed):"):rel.index("ds = [d for d in adates")].replace(
     "return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid)", "return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid, curve=Cv)"), globals())
NAME = {"P7":"외인 매집","P1":"조용한 신고가","P4":"업종붕괴 이탈","P6":"깊은 이격","P3":"폭락반등","P2":"조정매집","D1":"낙폭과대","D2":"저PBR 낙폭","P5":"자사주 낙폭"}

K=KP; g=K.groupby("ticker",sort=False); C,O,H,L,V=K.close,K.open,K.high,K.low,K.volume
sh=lambda s,n=1: s.groupby(K.ticker).shift(n)
green=C>O; pO,pC,pH,pL=sh(O),sh(C),sh(H),sh(L); pO2,pC2=sh(O,2),sh(C,2); pgreen=sh(green.astype(float))
ret20_2=sh(K.ret20,2)
harami=(pC2<pO2)&(pgreen==1)&(pH<=pO2)&(pL>=pC2)&green&(ret20_2<-10)
ma60=g.close.transform(lambda s: s.rolling(60).mean()); ret1=(C/pC-1)*100
g04b=(C<=0.8*ma60)&green&(ret1>=2)
gap_up=O>pH; pgap_dn=sh((O<pL).astype(float))
island=(pgap_dn>0)&gap_up&(O>pH)&(K.ret20<-10)
CAND = {
 "C08 잉태형+양봉 확인 (dn60·20일·4%·4)": (KP,20,None,4,4, base(KP,10)&dn60(KP)&harami),
 "G04b 60선-20% 급락반등 (dn60·20일·4%·4)": (KP,20,None,4,4, base(KP,10)&dn60(KP)&g04b),
 "C12 섬꼴반전 (dn60·20일·4%·4)": (KP,20,None,4,4, base(KP,10)&dn60(KP)&island),
}
# 겹침: 후보 신호일 ±5일 안에 기존 규칙 신호가 같은 종목에 있는 비율
S0 = build(RULES)
def overlap(cond):
    X = KP[cond.fillna(False)][["ticker","date"]]; X["di"]=X.date.map(ADI)
    ex = S0[["ticker","di"]] if "di" in S0.columns else S0.assign(di=S0.date.map(ADI))[["ticker","di"]]
    m = X.merge(ex, on="ticker", suffixes=("","_e")); hit = m[(m.di_e-m.di).abs()<=5][["ticker","di"]].drop_duplicates()
    return len(hit)/max(len(X),1), len(X)
PER=[("전체","20180101","20991231"),("학습","20180101","20221231"),("검증","20230101","20991231"),("붐제외","20180101","20241231")]
SEEDS=12; ds_all=[d for d in adates if d>="20180101"]; yrs=np.array([d[:4] for d in ds_all])
def run(R,d0="20180101",d1="20991231",seeds=SEEDS):
    S=build(R); ds=[d for d in adates if d0<=d<=d1]; return [sim(S,ds,k) for k in range(seeds)]
def yr_ret(runs):
    out={}
    for y in sorted(set(yrs)):
        idx=np.where(yrs==y)[0]; i0=max(idx[0]-1,0); i1=idx[-1]
        out[y]=np.array([(r["curve"].to_numpy()[i1]/r["curve"].to_numpy()[i0]-1)*100 for r in runs])
    return out
B={p[0]: run(RULES,p[1],p[2]) for p in PER}; BY=yr_ret(B["전체"])
print(f"기준 9규칙: " + " · ".join(f"{p[0]} {np.median([r['nav'] for r in B[p[0]]]):.2f}배" for p in PER) + f" · 낙폭 {np.median([r['mdd'] for r in B['전체']]):.1f}%\n")
def scaled(R,k): return {r:(K,h,s,p*k,m,c) for r,(K,h,s,p,m,c) in R.items()}
for nm,tup in CAND.items():
    ov,n = overlap(tup[5])
    R={**RULES,"N":tup}; res={p[0]: run(R,p[1],p[2]) for p in PER}
    cells=" · ".join(f"{p[0]} {np.median([r['nav'] for r in res[p[0]]]):.2f}({np.mean([a['nav']>b['nav'] for a,b in zip(res[p[0]],B[p[0]])])*100:.0f}%)" for p in PER)
    Y=yr_ret(res["전체"]); ys=[]; won=lost=0
    for y in sorted(Y):
        dm=np.median(Y[y])-np.median(BY[y])
        if abs(dm)<0.05: ys.append(f"{y[2:]}:="); continue
        won+=dm>0; lost+=dm<0; ys.append(f"{y[2:]}:{np.mean(Y[y]>BY[y])*100:.0f}%")
    print(f"━━ {nm} ━━  신호 {n}건 · 기존 규칙과 ±5일 겹침 {ov:.0%}")
    print(f"   {cells} · 낙폭 {np.median([r['mdd'] for r in res['전체']]):.1f}% · 이김 {won} 짐 {lost}  " + " ".join(ys))
    line="   자리 착시:"
    for k in (0.5,1.5):
        b=[r["nav"] for r in run(scaled(RULES,k))]; v=[r["nav"] for r in run(scaled(R,k))]
        line+=f"  ×{k} {np.median(b):.2f}→{np.median(v):.2f}({np.mean([a>c for a,c in zip(v,b)])*100:.0f}%)"
    print(line)
