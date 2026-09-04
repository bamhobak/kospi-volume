# -*- coding: utf-8 -*-
"""조임3(공매도<0.4·차익<-1.0) 정밀 — 24시드·연도별 짝비교·이웃 셀·보유기간·비중 스윕."""
exec(open("short_prog_ov.py",encoding="utf-8").read().split('KP["di"]=KP.date.map(ADI)')[0])
KP["di"]=KP.date.map(ADI)
PER=[("전체","20180101","20991231"),("학습","20180101","20221231"),("검증","20230101","20991231"),("붐제외","20180101","20241231")]
ds_all=[d for d in adates if d>="20180101"]; yrs=np.array([d[:4] for d in ds_all])
def run(R,d0,d1,seeds): S2=build(R); ds=[d for d in adates if d0<=d<=d1]; return [sim(S2,ds,k) for k in range(seeds)]
def yr_ret(runs):
    out={}
    for y in sorted(set(yrs)):
        idx=np.where(yrs==y)[0]; i0=max(idx[0]-1,0); i1=idx[-1]
        out[y]=np.array([(r["curve"].to_numpy()[i1]/r["curve"].to_numpy()[i0]-1)*100 for r in runs])
    return out
B24={p[0]: run(RULES,p[1],p[2],24) for p in PER}; BY=yr_ret(B24["전체"])
print("기준 9규칙(24시드): " + " · ".join(f"{p[0]} {np.median([r['nav'] for r in B24[p[0]]]):.2f}배" for p in PER)
      + f" · 낙폭 {np.median([r['mdd'] for r in B24['전체']]):.1f}%\n")
def rep(nm, cond, hold=20, pct=4, mx=4, seeds=24):
    R={**RULES,"N":(KP,hold,None,pct,mx, base(KP,30)&cond)}
    res={p[0]: run(R,p[1],p[2],seeds) for p in PER}
    cells=" · ".join(f"{p[0]} {np.median([r['nav'] for r in res[p[0]]]):.2f}({np.mean([a['nav']>b['nav'] for a,b in zip(res[p[0]],B24[p[0]])])*100:.0f}%)" for p in PER)
    Y=yr_ret(res["전체"]); won=lost=0; ys=[]
    for y in sorted(Y):
        dm=np.median(Y[y])-np.median(BY[y])
        if abs(dm)<0.05: ys.append(f"{y[2:]}:="); continue
        won+=dm>0; lost+=dm<0; ys.append(f"{y[2:]}:{np.mean(Y[y]>BY[y])*100:.0f}%")
    print(f"  {nm}\n    {cells} · 낙폭 {np.median([r['mdd'] for r in res['전체']]):.1f}% · 이김{won} 짐{lost}  "+" ".join(ys))
    return res
print("■ 조임3 이웃 셀 (24시드)")
for s,p in ((0.4,-1.0),(0.4,-0.7),(0.4,-1.5),(0.3,-1.0),(0.5,-1.0),(0.4,-2.0)):
    n=int((base(KP,30)&(KP.sr2<s)&(KP.pa20<p)).fillna(False).sum())
    rep(f"공매도<{s} · 차익<{p}  (원신호 {n:,}행)", (KP.sr2<s)&(KP.pa20<p))
print("\n■ 조임3 보유기간·비중 (24시드)")
C=(KP.sr2<0.4)&(KP.pa20<-1.0)
for h in (10,20,40,60): rep(f"보유 {h}일", C, hold=h)
for pct,mx in ((2,4),(4,2),(6,4),(4,6)): rep(f"비중 {pct}% · 최대 {mx}종목", C, pct=pct, mx=mx)
