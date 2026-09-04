# -*- coding: utf-8 -*-
"""유튜브 51편 3단계 — 기법의 '재료' 를 우리 9규칙에 얹어 본다 (규칙 단위 + 계좌 12시드 짝비교).
재료: 반전 캔들(관통·장악·잉태확인·망치) · 양봉 확인 · RSI<30 · 스토≤20 · VR≤70 · 60일 이격 ≤0.9 ·
      첫 반등일 · 거래량 침체 · 대량거래 급락일 회피/한정 · 20일선 이탈 조기청산.
사용: python tech51_c.py
"""
import io, sys, warnings; warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns); sys.stdout = real
KP, KQ, KB, RULES = ns["KP"], ns["KQ"], ns["KB"], ns["RULES"]
adates = sorted(set(KP.date)|set(KQ.date)); ADI = {d:i for i,d in enumerate(adates)}
rel = (BASE/"rules_relation.py").read_text(encoding="utf-8")
exec(rel[rel.index("def build(R):"):rel.index("S = build(RULES)")], globals())
exec(rel[rel.index("def sim(S, ds, seed):"):rel.index("ds = [d for d in adates")], globals())
NAME = {"P7":"외인 매집","P1":"조용한 신고가","P4":"업종붕괴 이탈","P6":"깊은 이격","P3":"폭락반등","P2":"조정매집","D1":"낙폭과대","D2":"저PBR 낙폭","P5":"자사주 낙폭"}

# ── 재료 계산(패널마다) ──
def feats(K):
    g = K.groupby("ticker", sort=False); C,O,H,L,V = K.close,K.open,K.high,K.low,K.volume
    sh = lambda s,n=1: s.groupby(K.ticker).shift(n)
    roll = lambda s,n,fn="mean": s.groupby(K.ticker).transform(lambda x: getattr(x.rolling(n),fn)())
    d=C.groupby(K.ticker).diff(); up=d.clip(lower=0); dn=(-d).clip(lower=0)
    au=up.groupby(K.ticker).transform(lambda x: x.ewm(alpha=1/14,adjust=False).mean()); ad=dn.groupby(K.ticker).transform(lambda x: x.ewm(alpha=1/14,adjust=False).mean())
    K["rsi14"]=100-100/(1+au/ad.replace(0,np.nan))
    l14=roll(L,14,"min"); h14=roll(H,14,"max"); K["stk14"]=(C-l14)/(h14-l14).replace(0,np.nan)*100
    sgn=np.sign(d).fillna(0); upv=V.where(sgn>0,0.0); dnv=V.where(sgn<0,0.0); eqv=V.where(sgn==0,0.0)
    K["vr25"]=(roll(upv,25,"sum")+roll(eqv,25,"sum")/2)/(roll(dnv,25,"sum")+roll(eqv,25,"sum")/2).replace(0,np.nan)*100
    K["ma60x"]=roll(C,60); K["v20x"]=roll(V,20); K["v5x"]=roll(V,5); K["v60x"]=roll(V,60)
    K["ret1x"]=C.pct_change().groupby(K.ticker).transform(lambda x: x)*100
    K["ret1x"]=(C/sh(C)-1)*100
    body=(C-O).abs(); rng=(H-L).replace(0,np.nan); pO,pC,pL=sh(O),sh(C),sh(L); pO2,pC2,pH,pL2=sh(O,2),sh(C,2),sh(H),sh(L,2)
    green=C>O; pgreen=sh(green.astype(float)); pbody=sh(body)
    K["c_hammer"]=((np.minimum(O,C)-L)>=2*body)&((H-np.maximum(O,C))<=0.1*rng+0.3*body)&(body<=0.35*rng)
    K["c_engulf"]=(pgreen==0)&green&(O<=pC)&(C>=pO)&(body>pbody)
    K["c_pierce"]=(pgreen==0)&green&(O<pL)&(C>(pO+pC)/2)&(C<pO)
    K["c_harami"]=(pC2<pO2)&(pgreen==1)&(pH<=pO2)&(sh(L)>=pC2)&green
    K["c_any"]=K.c_hammer|K.c_engulf|K.c_pierce|K.c_harami
    K["green"]=green
    K["bigcrash"]=(V>=3*K.v20x)&(K.ret1x<=-5)
    # 20일선 이탈 조기청산용: 진입 다음날부터 hold 일 안에 처음 종가<20일선 되는 날의 종가
    K["ma20x"]=roll(C,20)
for K in (KP,KQ): feats(K)
_F = pd.concat([KP[["ticker","date","rsi14","stk14","vr25","ma60x","v5x","v60x","ret1x","c_any","green","bigcrash","ma20x"]], KQ[["ticker","date","rsi14","stk14","vr25","ma60x","v5x","v60x","ret1x","c_any","green","bigcrash","ma20x"]]]).drop_duplicates(["ticker","date"])   # 시장을 옮긴 종목이 양쪽에 있을 수 있다
KB2 = KB.merge(_F, on=["ticker","date"], how="left"); del _F
assert len(KB2)==len(KB), (len(KB2), len(KB))
for c in ("rsi14","stk14","vr25","ma60x","v5x","v60x","ret1x","c_any","green","bigcrash","ma20x"): KB[c]=KB2[c].values
del KB2

MAT = {
 "반전 캔들(관통·장악·잉태·망치)": lambda K: K.c_any==True,
 "양봉 확인":                lambda K: K.green==True,
 "RSI14 < 30":             lambda K: K.rsi14<30,
 "스토 ≤ 20":               lambda K: K.stk14<=20,
 "VR25 ≤ 70":              lambda K: K.vr25<=70,
 "60일 이격 ≤ 0.90":         lambda K: K.close/K.ma60x<=0.90,
 "첫 반등일(+3%↑)":          lambda K: K.ret1x>=3,
 "거래량 침체(5일<0.5×60일)":  lambda K: K.v5x<0.5*K.v60x,
 "대량거래 급락일 제외":        lambda K: ~(K.bigcrash==True),
 "대량거래 급락일 한정":        lambda K: K.bigcrash==True,
}
def boot(v,k,seed=777,n=2000):
    if len(v)<25: return None
    rng=np.random.default_rng(seed); d=pd.DataFrame({"r":np.asarray(v),"ym":np.asarray(k)})
    ms=d.ym.unique(); by={m:d[d.ym==m].r.to_numpy() for m in ms}
    return np.percentile([np.concatenate([by[x] for x in rng.choice(ms,len(ms),replace=True)]).mean() for _ in range(n)],[2.5,97.5])
def rule_stats(K, hold, cond):
    col=f"n{hold}"
    if col not in K.columns:
        g=K.groupby("ticker",sort=False); K[col]=(g.close.shift(-hold)/K.buy-1)*100-K.cost
    X=K[cond.fillna(False)].dropna(subset=[col]).sort_values("date"); keep,last=[],{}
    for r in X.itertuples():
        i=ADI[r.date]
        if last.get(r.ticker,-10**9)>=i: continue
        last[r.ticker]=i+hold; keep.append(r.Index)
    Y=X.loc[keep]; r=Y[col]; ym=Y.date.str[:6]; IS=Y.date<"20230101"; NB=Y.date<"20250101"
    ca=boot(r[IS].values,ym[IS].values) if IS.sum()>=25 else None
    return dict(n=len(Y), avg=r.mean(), med=r.median(), win=(r>0).mean()*100, ci=ca, os=r[~IS].mean() if (~IS).sum() else np.nan)
def fmt_ci(c): return f"[{c[0]:+.1f},{c[1]:+.1f}]" if c is not None else "-"
PER=[("전체","20180101","20991231"),("검증","20230101","20991231"),("붐제외","20180101","20241231")]
SEEDS=8
def run(R,d0,d1):
    S=build(R); ds=[d for d in adates if d0<=d<=d1]; return [sim(S,ds,k)["nav"] for k in range(SEEDS)]
BASEN={p[0]: run(RULES,p[1],p[2]) for p in PER}
print("기준 계좌: " + " · ".join(f"{p[0]} {np.median(BASEN[p[0]]):.2f}배" for p in PER))

for rid,(K,hold,stop,pct,mx,cond) in RULES.items():
    b=rule_stats(K,hold,cond)
    print(f"\n━━━ [{NAME[rid]}] 원본 {b['n']}건 평균 {b['avg']:+.2f} 중앙 {b['med']:+.1f} 승률 {b['win']:.0f}% 학습CI {fmt_ci(b['ci'])} 검증 {b['os']:+.2f} ━━━")
    print(f"  {'재료':<28}{'n':>6}{'평균':>8}{'중앙':>7}{'승률':>6}{'검증':>8}  {'학습CI':<14} {'계좌 전체/검증/붐제외 (이긴 비율)'}")
    for mn,mf in MAT.items():
        c2=cond&mf(K)
        s=rule_stats(K,hold,c2)
        if s["n"]<25: print(f"  {mn:<28}{s['n']:>6} (부족)"); continue
        d=s["avg"]-b["avg"]; cells=""
        if d>0.3 and s["n"]>=40:          # 규칙 단위에서 좋아진 재료만 계좌로 보낸다(시간 절약)
            R2={**RULES, rid:(K,hold,stop,pct,mx,c2)}
            for p in PER:
                v=run(R2,p[1],p[2]); cells+=f" {np.median(v):.2f}({np.mean([a>bb for a,bb in zip(v,BASEN[p[0]])])*100:.0f}%)"
        else: cells=" (계좌 생략)"
        print(f"  {mn:<28}{s['n']:>6}{s['avg']:>+8.2f}{s['med']:>+7.1f}{s['win']:>5.0f}%{s['os']:>+8.2f}  {fmt_ci(s['ci']):<14}{cells}  {'▲' if d>0.5 else ('▼' if d<-0.5 else '=')}")
    # 20일선 이탈 조기청산 (규칙 단위)
    g=K.groupby("ticker",sort=False); C=K.close.to_numpy(float); M=K.ma20x.to_numpy(float); B=K.buy.to_numpy(float); T=K.ticker.to_numpy(); CO=K.cost.to_numpy(float)
    X=K[cond.fillna(False)].sort_values("date"); keep,last=[],{}
    for r in X.itertuples():
        i=ADI[r.date]
        if last.get(r.ticker,-10**9)>=i: continue
        last[r.ticker]=i+hold; keep.append(r.Index)
    idx=np.array(keep); out=[]; outf=[]
    for i in idx:
        e=i+1
        if e>=len(C) or T[e]!=T[i] or not B[i]>0: continue
        r=None; lastj=e
        for j in range(e,min(e+hold,len(C))):
            if T[j]!=T[i]: break
            lastj=j
            if j>e and C[j]<M[j]: r=(C[j]/B[i]-1)*100; break
        if r is None: r=(C[lastj]/B[i]-1)*100
        out.append(r-CO[i]); outf.append((C[lastj]/B[i]-1)*100-CO[i])
    if out: print(f"  {'20일선 이탈 조기청산':<28}{len(out):>6}{np.mean(out):>+8.2f}{np.median(out):>+7.1f}{np.mean(np.array(out)>0)*100:>5.0f}%   (같은 표본 고정보유 {np.mean(outf):+.2f})")
