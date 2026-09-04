# -*- coding: utf-8 -*-
"""유튜브 51편 2단계 — 1단계 통과·근접 규칙을 코스피 단독 · 국면별 · 연도별 · 경로 청산으로 다시 본다.
사용: python tech51_b.py "V01" "T03" ...   (규칙 태그 앞부분으로 지정)
"""
import sys, re
from tech51_ind import *
src = (BASE/"tech51_test.py").read_text(encoding="utf-8")
seg = src[src.index("# ── 규칙 정의"):src.index("# ── 실행")]
O,Hh,Ll,C,V = A.open,A.high,A.low,A.close,A.volume; up_c = C>O
exec(seg)
want = sys.argv[1:]
SEL = {k:v for k,v in R.items() if any(k.startswith(w) for w in want)}
print(f"대상 {len(SEL)}개 규칙 · 코스피 유니버스 20일 {base(20,mk='KOSPI'):+.2f}% · 국면별 UP {base(20,mk='KOSPI',reg='UP'):+.2f} / SIDE {base(20,mk='KOSPI',reg='SIDE'):+.2f} / DN {base(20,mk='KOSPI',reg='DN'):+.2f}\n")

# 경로 청산
Oa=O.to_numpy(float); Ha=Hh.to_numpy(float); La=Ll.to_numpy(float); Ca=C.to_numpy(float); M20=A.ma20.to_numpy(float)
TK=A.ticker.to_numpy(); COST=A.cost.to_numpy(float)
def path(idx, mode, max_hold):
    out=np.full(len(idx),np.nan)
    for n,i in enumerate(idx):
        e=i+1
        if e>=len(Oa) or TK[e]!=TK[i] or not Oa[e]>0: continue
        buy=Oa[e]; r=None; last=e; peak=buy
        for j in range(e,min(e+max_hold,len(Oa))):
            if TK[j]!=TK[i]: break
            last=j; peak=max(peak,Ha[j])
            if mode=="stop7" and La[j]<=buy*0.93: r=-7.0; break
            if mode=="trail10" and j>e and La[j]<=peak*0.90: r=(peak*0.90/buy-1)*100; break
            if mode=="ma20" and j>e and Ca[j]<M20[j]: r=(Ca[j]/buy-1)*100; break
        if r is None: r=(Ca[last]/buy-1)*100
        out[n]=r-COST[i]
    return out
def dedup(cond, hold, mk="KOSPI", reg=None):
    u=BASEU&(A.mk==mk)
    if reg: u&=(A.reg==reg)
    X=A[(u&cond).fillna(False)].sort_values("di"); keep,last=[],{}
    for r in X.itertuples():
        if last.get(r.ticker,-10**9)>=r.di: continue
        last[r.ticker]=r.di+hold; keep.append(r.Index)
    return X.loc[keep]
def judge(Y):
    if len(Y)<25: return "(부족)"
    Y=Y.copy(); Y["ym"]=Y.date.str[:6]; Y["yr"]=Y.date.str[:4]
    IS=Y[Y.date<"20230101"]; NB=Y[Y.yr<"2025"]
    ca=boot(IS.r.values,IS.ym.values); cn=boot(NB.r.values,NB.ym.values) if len(NB)>=25 else None
    trim=Y[Y.r<Y.r.quantile(.95)].r.mean()
    ok=(ca is not None and ca[0]>0 and cn is not None and cn[0]>0 and Y.r.median()>0 and NB.r.median()>0 and trim>0)
    return (f"{len(Y):>5} 평균 {Y.r.mean():>+6.2f} 승률 {(Y.r>0).mean():>4.0%} 중앙 {Y.r.median():>+5.1f} 상5뺀 {trim:>+5.2f} "
            f"학습CI {f(ca)} 붐제외CI {f(cn)}{'  ✅' if ok else ''}")

for tag, cond in SEL.items():
    print(f"\n━━━ {tag} ━━━")
    print("  코스피 고정 보유"); hdr()
    for h in (5,10,20,40,60): go(f"  {h}일", cond, hold=h, mk="KOSPI", minn=25)
    print("  코스닥 고정 보유"); hdr()
    for h in (5,20,60): go(f"  {h}일", cond, hold=h, mk="KOSDAQ", minn=25)
    print("  국면별(코스피·20일)"); hdr()
    for rg in ("UP","SIDE","DN"): go(f"  {rg}", cond, hold=20, mk="KOSPI", reg=rg, minn=25)
    print("  경로 청산(코스피)")
    for mode,mh in (("stop7",20),("trail10",40),("ma20",40)):
        Y=dedup(cond,mh); Y=Y.copy(); Y["r"]=path(Y.index.to_numpy(),mode,mh); Y=Y.dropna(subset=["r"])
        print(f"    {mode:<8} 최대{mh}일 {judge(Y)}")
    print("  연도별(코스피·20일)")
    Y=go("  ", cond, hold=20, mk="KOSPI", minn=1, quiet=True)
    if len(Y):
        yr=Y.groupby("yr").agg(n=("r","size"),avg=("r","mean"),win=("r",lambda s:(s>0).mean()*100),al=("alpha","mean"))
        print("    "+" · ".join(f"{y}:{int(r.n)}건 {r.avg:+.1f}%({r.win:.0f}%)" for y,r in yr.iterrows()))
        top=Y.yr.value_counts(normalize=True).max(); print(f"    최다 연도 비중 {top:.0%}")
