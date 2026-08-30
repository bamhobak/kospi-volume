# -*- coding: utf-8 -*-
"""재설정: 절대수익 기준 + 국면 양립성
   채택 원칙 = 상승장(지수 60일선 위)과 하락장(아래) '양쪽 모두'에서 수익을 올리는 조건만.
   학습기간(2018~22)에서만 판단한다.
"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/bull_feat.pkl"); IS=D[D.y<=2022]
UP,DN=IS[IS.k60],IS[~IS.k60]

print("## 기준선 — 절대수익(비용 차감), 학습기간\n")
print("| 국면 | 10일 | 20일 | 40일 |\n|---|---|---|---|")
for lab,x in [("상승장(60일선 위)",UP),("하락장(아래)",DN),("전체",IS)]:
    print(f"| {lab} | "+" | ".join(f"{x[f'n{h}'].mean():+.2f}%" for h in (10,20,40))+" |")

def conds(B):
    C=[]
    a=lambda nm,s:C.append((nm,s))
    for q in (30,50,80,120,200): a(f"거래량침체 r16<{q}",B.r16<q)
    for q in (150,200,300): a(f"거래량급증 rw1>={q}",B.rw1>=q)
    for q in (80,120): a(f"거래량잠잠 rw1<={q}",B.rw1<=q)
    for q in (2,3,5): a(f"당일급증 su1>={q}",B.su1>=q)
    for q in (1,3,5,10): a(f"외국인5일>={q}",B.fw5>=q)
    for q in (0.5,1,2,3): a(f"외국인60일>={q}",B.fw60>=q)
    for q in (0,1,2): a(f"기관5일>={q}",B.ow5>=q)
    for q in (0,1): a(f"기관20일>={q}",B.ow20>=q)
    for q in (-20,-10,-5,0): a(f"20일수익<={q}",B.ret20<=q)
    for q in (0,5,10,20): a(f"20일수익>={q}",B.ret20>=q)
    for q in (-30,-20,-10): a(f"60일수익<={q}",B.ret60<=q)
    for q in (0,10,20): a(f"60일수익>={q}",B.ret60>=q)
    for q in (-50,-30,-20,-10,-5): a(f"고점대비<={q}",B.fromhi<=q)
    for q in (-10,-5,-3): a(f"신고가근접>={q}",B.fromhi>=q)
    for q in (10,20,50): a(f"저점대비<={q}",B.fromlo<=q)
    for q in (3,5,10,20,50,100): a(f"거래대금>={q}억",B.amt20>=q)
    for q in (10,30,100): a(f"거래대금<={q}억",B.amt20<=q)
    for q in (2,3,4): a(f"변동성<={q}",B.vol20<=q)
    for q in (4,5): a(f"변동성>={q}",B.vol20>=q)
    a("공매도감소",B.srd==True); a("공매도증가",B.srd==False)
    for q in (1,3): a(f"공매도비중<={q}",B.sr20<=q)
    a("증자없음",~B.dil)
    a("clv>=0.7",B.clv>=0.7); a("clv<=0.3",B.clv<=0.3)
    for q in (-3,0,3): a(f"익일갭<={q}",B.gap<=q)
    for q in (-10,-5,0): a(f"20일선이격<={q}",B.dma20<=q)
    for q in (0,5,10): a(f"20일선이격>={q}",B.dma20>=q)
    for q in (-10,0,5): a(f"60일선이격>={q}",B.dma60>=q)
    return C

for h in (20,40):
    bu,bd=UP[f"n{h}"].mean(),DN[f"n{h}"].mean()
    print(f"\n## 단일조건 · {h}일 보유 — 상승장/하락장 동시 성립 (기준 상승 {bu:+.2f}% / 하락 {bd:+.2f}%)\n")
    CU,CD=dict(conds(UP)),dict(conds(DN))
    R=[]
    for nm in CU:
        u=UP[CU[nm].fillna(False)][f"n{h}"].dropna(); d=DN[CD[nm].fillna(False)][f"n{h}"].dropna()
        if len(u)<300 or len(d)<300: continue
        R.append((nm,len(u),u.mean(),len(d),d.mean(),min(u.mean()-bu,d.mean()-bd)))
    R.sort(key=lambda r:-r[5])
    print("| 조건 | 상승장 표본 | **상승장 수익** | 하락장 표본 | **하락장 수익** | 약한쪽 개선 |\n|---|---|---|---|---|---|")
    for nm,nu,mu,nd,md,w in R[:14]:
        print(f"| {nm} | {nu:,} | **{mu:+.2f}%** | {nd:,} | **{md:+.2f}%** | {w:+.2f}%p |")
    bad=[r for r in R if r[5]<0][-4:]
    print("\n한쪽에서 무너지는 조건: "+", ".join(f"{nm}(상{mu:+.1f}/하{md:+.1f})" for nm,_,mu,_,md,_ in bad))
