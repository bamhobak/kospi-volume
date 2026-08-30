# -*- coding: utf-8 -*-
"""업종 상대강도 실측 — 코스피·코스닥 동시. 안정성(승률·중앙값) 기준.
   업종지표: 업종 20/60일 수익률 · 업종 내 순위 · 종목-업종 괴리(상대강도) · 업종 모멘텀 전환
"""
import io,sys,csv,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
IND={}
for r in csv.DictReader(open("data/industry.csv",encoding="utf-8-sig")):
    k=list(r.values()); IND[k[0]]=k[-1]
def prep(path,label):
    D=pd.read_pickle(path)
    D["up"]=D.ticker.map(IND)
    d=D[D.up.notna()].copy()
    # 업종 수익률 (소속 종목 중앙값)
    for w in (20,60):
        m=d.dropna(subset=[f"ret{w}"]).groupby(["date","up"])[f"ret{w}"].median()
        D[f"u{w}"]=pd.MultiIndex.from_arrays([D.date,D.up]).map(m)
    # 업종 내 종목 순위 (백분위) — 60일 수익 기준
    D["urank"]=D.groupby(["date","up"]).ret60.rank(pct=True)*100
    # 종목-업종 괴리
    D["rs20"]=D.ret20-D.u20
    D["rs60"]=D.ret60-D.u60
    # 업종 자체의 시장 대비 강도 (전체 업종 중 백분위)
    D["uprank"]=D.groupby("date").u60.rank(pct=True)*100
    # 업종 모멘텀 전환: 업종 60일은 마이너스인데 20일은 플러스
    D["uturn"]=((D.u60<0)&(D.u20>0))
    print(f"{label}: 업종 매핑 {D.up.notna().mean()*100:.0f}% · u60 채움 {D.u60.notna().mean()*100:.0f}%")
    return D
K=prep("data/bull_feat.pkl","코스피"); Q=prep("data/kd_feat.pkl","코스닥")
def scan(D,label,h,safe):
    B=D[safe&(D.y<=2022)]
    base=B[f"n{h}"].dropna()
    print(f"\n## {label} · {h}일 보유 — 기준선 승률 {(base>0).mean()*100:.0f}% 중앙 {np.median(base):+.2f}% 평균 {base.mean():+.2f}%\n")
    C=[]
    a=lambda nm,s:C.append((nm,s))
    for q in (-20,-10,0,10): a(f"업종60일 ≤ {q}%",B.u60<=q)
    for q in (0,5,10,20): a(f"업종60일 ≥ {q}%",B.u60>=q)
    for q in (-10,0): a(f"업종20일 ≤ {q}%",B.u20<=q)
    for q in (0,5): a(f"업종20일 ≥ {q}%",B.u20>=q)
    a("업종 모멘텀 전환(60일-·20일+)",B.uturn)
    for q in (20,50,80): a(f"업종강도 상위 {100-q}%",B.uprank>=q)
    for q in (20,50): a(f"업종강도 하위 {q}%",B.uprank<=q)
    for q in (20,50,80): a(f"업종 내 순위 상위 {100-q}%",B.urank>=q)
    for q in (20,50): a(f"업종 내 순위 하위 {q}%",B.urank<=q)
    for q in (-20,-10,0): a(f"업종대비 60일 ≤ {q}%p",B.rs60<=q)
    for q in (0,10,20): a(f"업종대비 60일 ≥ {q}%p",B.rs60>=q)
    for q in (-10,0): a(f"업종대비 20일 ≤ {q}%p",B.rs20<=q)
    for q in (0,10): a(f"업종대비 20일 ≥ {q}%p",B.rs20>=q)
    R=[]
    for nm,s in C:
        x=B[s.fillna(False)][f"n{h}"].dropna()
        if len(x)<3000: continue
        R.append((nm,len(x),x.mean(),np.median(x),(x>0).mean()*100,np.percentile(x,5)))
    R.sort(key=lambda r:-r[4])
    print("| 업종 조건 | 표본 | 평균 | 중앙값 | **승률** | 하위5% |\n|---|---|---|---|---|---|")
    for nm,n,m,md,w,p5 in R[:8]:
        print(f"| {nm} | {n:,} | {m:+.2f}% | {md:+.2f}% | **{w:.0f}%** | {p5:.1f}% |")
    print("하위 3: "+" · ".join(f"{nm}(승률 {w:.0f}%)" for nm,_,_,_,w,_ in R[-3:]))
SK=((K.close>=1000)&(~K.dil)&(K.amt20>=10)).fillna(False)
SQ=((Q.close>=1000)&(~Q.dil)&(Q.amt20>=5)).fillna(False)
for h in (20,40): scan(K,"코스피",h,SK)
for h in (20,40): scan(Q,"코스닥",h,SQ)
K.to_pickle("data/kp_up.pkl"); Q.to_pickle("data/kq_up.pkl")
