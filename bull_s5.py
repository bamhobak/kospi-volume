# -*- coding: utf-8 -*-
"""신고가·거래량침체 계열 — 절대수익 기준.
   목표 재정의: 상승장에서 '번다' + 하락장에서 '버틴다(크게 잃지 않는다)'.
   선별은 학습기간 상승장 수익으로만. 하락장은 생존성 점검용.
"""
import io,sys,pickle,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/bull_feat.pkl"); IS=D[D.y<=2022]

def mask(d,p):
    m=(~d.dil)&(d.amt20>=p["amt"])&(d.fromhi>=p["fh"])
    for k,f in [("r16",lambda v:d.r16<v),("rw1",lambda v:d.rw1<=v),("fw5",lambda v:d.fw5>=v),
                ("fw60",lambda v:d.fw60>=v),("vol",lambda v:d.vol20<=v),("sr",lambda v:d.sr20<=v),
                ("ret20",lambda v:d.ret20<=v),("ret60",lambda v:d.ret60<=v),("clv",lambda v:d.clv>=v)]:
        if p.get(k) is not None: m&=f(p[k])
    if p["srd"]: m&=(d.srd==True)
    if p["k20"]: m&=d.k20
    return m.fillna(False)

G=[]
for fh in (-5,-10):
 for r16 in (50,80,120,None):
  for rw1 in (120,None):
   for fw5 in (3,None):
    for fw60 in (1,None):
     for vol in (3,4,None):
      for sr in (1,3,None):
       for ret20 in (10,None):
        for srd in (True,False):
         for k20 in (True,False):
          for amt in (3,10):
           G.append(dict(fh=fh,r16=r16,rw1=rw1,fw5=fw5,fw60=fw60,vol=vol,sr=sr,ret20=ret20,srd=srd,k20=k20,amt=amt))
print(f"후보 {len(G):,}개 · 학습기간 상승장 수익으로만 선별\n")
UPm=IS.k60.values; DNm=(~IS.k60).values
rows=[]
for p in G:
    m=mask(IS,p).values
    for h in (20,40):
        col=IS[f"n{h}"].values
        u=col[m&UPm]; u=u[np.isfinite(u)]
        if len(u)<200: continue
        d=col[m&DNm]; d=d[np.isfinite(d)]
        rows.append((p,h,len(u),u.mean(),np.median(u),(u>0).mean()*100,len(d),d.mean() if len(d) else np.nan))
rows.sort(key=lambda r:-r[3])
def desc(p):
    q=[f"신고가{p['fh']}%이내"]
    for k,lab in [("r16","거래량침체<"),("rw1","단기거래량<="),("fw5","외인5일>="),("fw60","외인60일>="),
                  ("vol","변동성<="),("sr","공매도비중<="),("ret20","20일수익<=")]:
        if p.get(k) is not None: q.append(f"{lab}{p[k]}")
    if p["srd"]: q.append("공매도감소")
    if p["k20"]: q.append("지수20일선위")
    q.append(f"{p['amt']}억+")
    return " · ".join(q)
print("## 학습기간 상승장 상위 15\n")
print("| # | 조건 | 보유 | 표본 | **상승장 수익** | 중앙값 | 승률 | 하락장 표본 | 하락장 수익 |\n|---|---|---|---|---|---|---|---|---|")
for i,(p,h,n,m_,md,w,nd,dm) in enumerate(rows[:15],1):
    print(f"| {i} | {desc(p)} | {h}일 | {n:,} | **{m_:+.2f}%** | {md:+.2f}% | {w:.0f}% | {nd:,} | {dm:+.2f}% |")
pickle.dump(rows[:40],open("data/bull_cand2.pkl","wb"))
print("\n상위 40 저장")
