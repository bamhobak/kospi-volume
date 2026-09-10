# -*- coding: utf-8 -*-
"""[자사주 낙폭] **사건형** 의 계좌 기여 — 설명문에 적을 숫자를 사건형으로 다시 잰다.

앞서 잰 계좌(12.09배)는 상태형 기준이었다. 중복제거 뒤에는 두 형태가 거의 같지만
(1,507건 vs 1,441건) 화면에 적는 숫자는 실제로 쓰는 형태로 재야 한다.
자리 3 · 5 두 가지를 본다.
"""
src=open("us_buyback5.py",encoding="utf-8").read()
exec(src.split('print("\n" + "=" * 148)')[0].split('"""',2)[2])
PURE=((K.fromhi<=-30)&K.sp60&(K.ret20<=-20)).fillna(False)
def ev(st,w=20):
    seen=(st.groupby(K.ticker).shift(1).fillna(False).astype(bool)
          .groupby(K.ticker).transform(lambda s:s.rolling(w,min_periods=1).max()).fillna(0)>0)
    return (st&~seen).fillna(False)
N4=(ev(PURE,20)&UNI).fillna(False)
gg=K.groupby("ticker",sort=False)
K["a20b"]=gg.volume.transform(lambda s:s.shift(3).rolling(20).mean())
K["re_mo"]=K.vm3/K.a20b*100
_w=(K.fromhi>=-5).fillna(False)
_seen=(_w.groupby(K.ticker).shift(1).fillna(False).astype(bool)
       .groupby(K.ticker).transform(lambda s:s.rolling(20,min_periods=1).max()).fillna(0)>0)
N1=(UNI&UP&_w&~_seen&(K.re_mo<=100)).fillna(False)
U2=K.amt20.fillna(0)>=2.0
DEBT=K["부채비율"] if "부채비율" in K.columns else pd.Series(np.nan,index=K.index)
D1c=(U2&DN&(K.ret20<=-30)&(K.su1>=2)&(K.u<=-10)&(DEBT.isna()|(DEBT<=200))).fillna(False)
D2c=(U2&DN&(K.PBR>0)&(K.PBR<=0.8)&(K.ret20<=-10)&(K.su1>=2)&(K.u<=-10)).fillna(False)
def tb(cond,h):
    X=K[cond.fillna(False)].dropna(subset=[f"n{h}"]).sort_values("di")
    keep,last=[],{}
    for t,i,ix in zip(X.ticker.values,X.di.values,X.index):
        if last.get(t,-10**9)>=i: continue
        last[t]=i+h; keep.append(ix)
    d=X.loc[keep].copy(); d=d[(d.date>="20160101")&(d.buy>0)]
    d["ret"]=d[f"n{h}"].astype(float); d["hold"]=h
    return d[["date","ticker","hold","ret","di","amt20"]]
def build(extra=None):
    P=[("D1",tb(D1c,20),5,3),("D2",tb(D2c,40),5,3),("N1",tb(N1,40),5,8)]
    if extra: P.append(extra)
    return pd.concat([t.assign(rid=r,pct=p,mx=m) for r,t,p,m in P],ignore_index=True).sort_values("di").reset_index(drop=True)
def sim(S,ds,seed=None):
    rng=np.random.default_rng(seed) if seed is not None else None
    nav,held,cnt=1.0,{},{}; peak,mdd,inv=1.0,0.0,[]
    byd={d:g for d,g in S[S.date.isin(set(ds))].groupby("date")}
    for d in ds:
        di=ADI[d]
        for k in [k for k,v in held.items() if v[0]<=di]:
            nav*=1+held.pop(k)[1]/100; cnt[k[0]]=cnt.get(k[0],0)-1
        peak=max(peak,nav); mdd=min(mdd,nav/peak-1); inv.append(sum(x[3] for x in held.values()))
        g2=byd.get(d)
        if g2 is None: continue
        g2=(g2.sample(frac=1,random_state=int(rng.integers(1<<30))) if rng is not None
            else g2.sort_values("amt20",ascending=False,na_position="last"))
        for r_ in g2.itertuples():
            if cnt.get(r_.rid,0)>=r_.mx: continue
            k=(r_.rid,r_.ticker,d)
            if k in held or sum(x[3] for x in held.values())+r_.pct/100>1.0: continue
            held[k]=(di+int(r_.hold),r_.ret*r_.pct/100,r_.rid,r_.pct/100); cnt[r_.rid]=cnt.get(r_.rid,0)+1
    for v in held.values(): nav*=1+v[1]/100
    return nav,mdd*100,float(np.mean(inv))
PER=[("학습","20160101","20221231"),("검증","20230101","20991231"),("기준","20160101","20991231")]
DS={p[0]:[d for d in ud if p[1]<=d<=p[2]] for p in PER}
print(f"  {'구성':<28}{'학습':>10}{'검증':>10}{'기준':>10}{'낙폭':>7}{'투입':>7}{'랜중앙':>10}{'랜최악':>10}")
for nm,ex in (("기존 3규칙만",None),
              ("+ 자사주 사건형 60일 (자리3)",("BB",tb(N4,60),5,3)),
              ("+ 자사주 사건형 60일 (자리5)",("BB",tb(N4,60),5,5))):
    S=build(ex); res=[sim(S,DS[p[0]]) for p in PER]
    R=[sim(S,DS["기준"],seed=k) for k in range(30)]
    nav=np.array([x[0] for x in R])
    print(f"  {nm:<28}"+"".join(f"{x[0]:>9.2f}배" for x in res)+
          f"{res[2][1]:>6.0f}%{res[2][2]*100:>6.0f}%{np.median(nav):>9.2f}배{nav.min():>9.2f}배",flush=True)
