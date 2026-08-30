# -*- coding: utf-8 -*-
"""조합 조립 — 절대수익 기준 · 상승/하락 양쪽 성립 요구 · 학습기간(2018~22)에서만 선별"""
import io,sys,pickle,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/bull_feat.pkl"); IS=D[D.y<=2022]

def mask(d,p):
    m=(~d.dil)&(d.amt20>=p["amt"])
    if p["sr"] is not None: m&=(d.sr20<=p["sr"])
    if p["srd"]: m&=(d.srd==True)
    if p["dma"] is not None: m&=(d.dma20<=p["dma"])
    if p["ret20"] is not None: m&=(d.ret20<=p["ret20"])
    if p["fh"] is not None: m&=(d.fromhi<=p["fh"])
    if p["fw"] is not None: m&=(d.fw60>=p["fw"])
    if p["fw5"] is not None: m&=(d.fw5>=p["fw5"])
    if p["su"] is not None: m&=(d.su1>=p["su"])
    if p["vol"] is not None: m&=(d.vol20<=p["vol"])
    if p["clv"] is not None: m&=(d.clv>=p["clv"])
    return m.fillna(False)

G=[]
for sr in (1,3,None):
 for srd in (True,False):
  for dma in (-5,-10,None):
   for ret20 in (-10,None):
    for fh in (-20,-30,None):
     for fw in (1,None):
      for fw5 in (3,None):
       for su in (2,None):
        for vol in (4,None):
         for clv in (0.5,None):
          for amt in (3,10):
           G.append(dict(sr=sr,srd=srd,dma=dma,ret20=ret20,fh=fh,fw=fw,fw5=fw5,su=su,vol=vol,clv=clv,amt=amt))
print(f"후보 {len(G):,}개 조합 · 보유 20/40일 · 학습기간에서만 선별\n")
UPm,DNm=IS.k60.values,(~IS.k60).values
rows=[]
for p in G:
    m=mask(IS,p).values
    if m.sum()<400: continue
    for h in (20,40):
        col=IS[f"n{h}"].values
        u=col[m&UPm]; d=col[m&DNm]
        u=u[np.isfinite(u)]; d=d[np.isfinite(d)]
        if len(u)<150 or len(d)<150: continue
        if u.mean()<=0 or d.mean()<=0: continue          # 양쪽 모두 (+) 요구
        a=col[m]; a=a[np.isfinite(a)]
        rows.append((p,h,len(a),a.mean(),len(u),u.mean(),len(d),d.mean(),min(u.mean(),d.mean())))
print(f"양쪽 (+) 통과 {len(rows):,}개\n")
rows.sort(key=lambda r:-r[8])           # 약한 쪽(min) 기준 — 어느 국면에서도 버티는 것 우선
def desc(p):
    q=[]
    if p["sr"] is not None: q.append(f"공매도비중<={p['sr']}")
    if p["srd"]: q.append("공매도감소")
    if p["dma"] is not None: q.append(f"20일선이격<={p['dma']}%")
    if p["ret20"] is not None: q.append(f"20일수익<={p['ret20']}%")
    if p["fh"] is not None: q.append(f"고점대비<={p['fh']}%")
    if p["fw"] is not None: q.append(f"외인60일>={p['fw']}")
    if p["fw5"] is not None: q.append(f"외인5일>={p['fw5']}")
    if p["su"] is not None: q.append(f"당일거래량>={p['su']}배")
    if p["vol"] is not None: q.append(f"변동성<={p['vol']}")
    if p["clv"] is not None: q.append(f"종가위치>={p['clv']}")
    q.append(f"{p['amt']}억+")
    return " · ".join(q)
print("## 학습기간 상위 15 (약한 국면 수익 순)\n")
print("| # | 조건 | 보유 | 전체 | 전체수익 | 상승장 | **상승장수익** | 하락장 | **하락장수익** |\n|---|---|---|---|---|---|---|---|---|")
for i,(p,h,n,mn,nu,mu,nd,md,w) in enumerate(rows[:15],1):
    print(f"| {i} | {desc(p)} | {h}일 | {n:,} | {mn:+.2f}% | {nu:,} | **{mu:+.2f}%** | {nd:,} | **{md:+.2f}%** |")
pickle.dump(rows[:40],open("data/bull_cand.pkl","wb"))
print(f"\n상위 40개 저장. 다음: 검증기간(2023~26) 확인")
