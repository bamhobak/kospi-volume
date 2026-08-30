# -*- coding: utf-8 -*-
"""신고가 계열 검증 — 학습에서 고른 40개를 검증기간(2023~26)에서 한 번만"""
import io,sys,pickle,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/bull_feat.pkl"); OS=D[D.y>=2023]
rows=pickle.load(open("data/bull_cand2.pkl","rb"))
def mask(d,p):
    m=(~d.dil)&(d.amt20>=p["amt"])&(d.fromhi>=p["fh"])
    for k,f in [("r16",lambda v:d.r16<v),("rw1",lambda v:d.rw1<=v),("fw5",lambda v:d.fw5>=v),
                ("fw60",lambda v:d.fw60>=v),("vol",lambda v:d.vol20<=v),("sr",lambda v:d.sr20<=v),
                ("ret20",lambda v:d.ret20<=v),("clv",lambda v:d.clv>=v)]:
        if p.get(k) is not None: m&=f(p[k])
    if p["srd"]: m&=(d.srd==True)
    if p["k20"]: m&=d.k20
    return m.fillna(False)
UP=OS.k60.values
print("## 검증기간(2023~26) — 40개 중 상위 15 표시\n")
print("| # | 보유 | 학습상승 | **검증 상승장** | (건수) | 승률 | 중앙값 | **검증 하락장** | (건수) | 검증전체 |")
print("|---|---|---|---|---|---|---|---|---|---|")
K=[]
for i,(p,h,n,m_,md,w,nd,dm) in enumerate(rows,1):
    m=mask(OS,p).values; col=OS[f"n{h}"].values
    u=col[m&UP]; u=u[np.isfinite(u)]
    d=col[m&~UP]; d=d[np.isfinite(d)]
    a=col[m]; a=a[np.isfinite(a)]
    K.append((i,p,h,m_,u,d,a))
    if i<=15:
        print(f"| {i} | {h}일 | {m_:+.1f}% | **{u.mean():+.2f}%** | {len(u)} | {(u>0).mean()*100:.0f}% | {np.median(u):+.2f}% | "
              f"**{d.mean() if len(d) else float('nan'):+.2f}%** | {len(d)} | {a.mean():+.2f}% |")
uu=[k[4].mean() for k in K if len(k[4])>=30]
print(f"\n**40개 전체 검증 분포 (상승장)** — 중앙값 {np.median(uu):+.2f}% · 양수 {sum(1 for v in uu if v>0)}/{len(uu)}개 · "
      f"최저 {min(uu):+.2f}% · 최고 {max(uu):+.2f}%")
dd=[k[5].mean() for k in K if len(k[5])>=30]
print(f"**하락장** — 중앙값 {np.median(dd):+.2f}% · 양수 {sum(1 for v in dd if v>0)}/{len(dd)}개")
print(f"\n검증기간 기준선: 상승장 40일 아무거나 = {OS[OS.k60].n40.mean():+.2f}% · 하락장 = {OS[~OS.k60].n40.mean():+.2f}%")
print(f"→ 40개 중 기준선을 넘은 것: {sum(1 for v in uu if v>OS[OS.k60].n40.mean())}/{len(uu)}개")
pickle.dump(K,open("data/bull_val2.pkl","wb"))
