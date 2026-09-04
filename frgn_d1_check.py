# -*- coding: utf-8 -*-
"""[낙폭과대] + '1년 평균 외인 지분율 < 2%' 정밀 검증 — 이웃 문턱·자리 착시·24시드·연도별."""
exec(open("frgn_overlay.py",encoding="utf-8").read().split("PER=[")[0])
PER=[("전체","20180101","20991231"),("학습","20180101","20221231"),("검증","20230101","20991231"),("붐제외","20180101","20241231")]
ds_all=[d for d in adates if d>="20180101"]; yrs=np.array([d[:4] for d in ds_all])
def run(R,d0,d1,seeds): S=build(R); ds=[d for d in adates if d0<=d<=d1]; return [sim(S,ds,k) for k in range(seeds)]
def yr_ret(runs):
    out={}
    for y in sorted(set(yrs)):
        idx=np.where(yrs==y)[0]; i0=max(idx[0]-1,0); i1=idx[-1]
        out[y]=np.array([(r["curve"].to_numpy()[i1]/r["curve"].to_numpy()[i0]-1)*100 for r in runs])
    return out
K,hold,stop,pct,mx,cond = RULES["D1"]
print("이웃 문턱 (규칙 단위 · [낙폭과대] · 20일)"); print(f"  {'문턱':<22}{'n':>5}{'평균':>8}{'중앙':>7}{'승률':>6}{'검증':>8}  학습CI          붐제외CI")
for th in (1.0,1.5,2.0,2.5,3.0,4.0):
    s=stats(K,hold,cond&(K.fr250<th))
    if s["n"]<25: print(f"  지분율 < {th}%{'':<10}{s['n']:>5} (부족)"); continue
    ok = (s["ci"] is not None and s["ci"][0]>0) and (s["cn"] is not None and s["cn"][0]>0) and s["med"]>0
    print(f"  지분율 < {th}%{'':<10}{s['n']:>5}{s['avg']:>+8.2f}{s['med']:>+7.1f}{s['win']:>5.0f}%{s['os']:>+8.2f}  {fci(s['ci']):<15}{fci(s['cn']):<15}{'✅' if ok else ''}")
print("  ── 여집합(지분율 ≥2%) ──")
s=stats(K,hold,cond&(K.fr250>=2)); print(f"  지분율 ≥ 2%{'':<10}{s['n']:>5}{s['avg']:>+8.2f}{s['med']:>+7.1f}{s['win']:>5.0f}%{s['os']:>+8.2f}  {fci(s['ci']):<15}{fci(s['cn']):<15}")
s=stats(K,hold,cond&K.fr250.isna()); print(f"  지분율 결측{'':<12}{s['n']:>5}{s['avg']:>+8.2f}{s['med']:>+7.1f}{s['win']:>5.0f}%{s['os']:>+8.2f}")
C2 = cond&(K.fr250<2)
R2={**RULES,"D1":(K,hold,stop,pct,mx,C2)}
print("\n계좌 24시드 짝비교")
B24={}; V24={}
for nm,d0,d1 in PER:
    b=run(RULES,d0,d1,24); v=run(R2,d0,d1,24); B24[nm]=b; V24[nm]=v
    print(f"  {nm:<6} {np.median([r['nav'] for r in b]):.2f}→{np.median([r['nav'] for r in v]):.2f}배 ({np.mean([a['nav']>c['nav'] for a,c in zip(v,b)])*100:>3.0f}%)")
print(f"  낙폭 {np.median([r['mdd'] for r in B24['전체']]):.1f}% → {np.median([r['mdd'] for r in V24['전체']]):.1f}%")
BY=yr_ret(B24["전체"]); VY=yr_ret(V24["전체"]); won=lost=0; ys=[]
for y in sorted(BY):
    dm=np.median(VY[y])-np.median(BY[y])
    if abs(dm)<0.05: ys.append(f"{y[2:]}:="); continue
    won+=dm>0; lost+=dm<0; ys.append(f"{y[2:]}:{np.mean(VY[y]>BY[y])*100:.0f}%")
print(f"  연도별 이김{won} 짐{lost}  " + " ".join(ys))
def scaled(R,k): return {r:(KK,h,s,p*k,m,c) for r,(KK,h,s,p,m,c) in R.items()}
line="  자리 착시:"
for k in (0.5,1.5):
    b=[r["nav"] for r in run(scaled(RULES,k),"20180101","20991231",12)]; v=[r["nav"] for r in run(scaled(R2,k),"20180101","20991231",12)]
    line+=f"  ×{k} {np.median(b):.2f}→{np.median(v):.2f}({np.mean([a>c for a,c in zip(v,b)])*100:.0f}%)"
print(line)
Y=stats(K,hold,C2)["Y"]; Y=Y.assign(yr=Y.date.str[:4])
print("\n  규칙 단위 연도별: "+" · ".join(f"{y}:{int(len(x))}건 {x[f'n{hold}'].mean():+.1f}%" for y,x in Y.groupby("yr")))
print(f"  최다 연도 비중 {Y.yr.value_counts(normalize=True).max():.0%}")
