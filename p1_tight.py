# -*- coding: utf-8 -*-
"""P1(조용한 신고가) 강화 — 거래건수를 줄이고 안전성을 올린다. 수익 감소 감수.
   안전성 = 승률·중앙값·PF 상승 + 최악/하위5% 완화. 선별은 학습(2018~22), 확인은 검증(2023~26).
"""
import io,sys,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
D=pd.read_pickle("data/bull_feat.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
g=D.groupby("ticker",sort=False)
D["ret250"]=g.close.transform(lambda x:x/x.shift(250)-1)*100
D["above20"]=g.close.transform(lambda x:(x>x.rolling(20).mean()).rolling(250,min_periods=60).mean())*100
D["lo40"]=g.low.shift(-1).rolling(40,min_periods=1).min().shift(-39)
BASE=(((D.fromhi>=-10)&(D.r16<120)&(D.rw1<=120)&(D.fw5>=3)&(D.fw60>=1)&(D.vol20<=3)
      &(D.sr20<=1)&(D.ret20<=10)&(D.amt20>=50)&(~D.dil)).fillna(False)
      & ~((D.above20>70)&(D.ret250>120)).fillna(False))
X=D[BASE].copy()
def st(s,lab,n0=None):
    a=s[s.y<=2022].n40.dropna(); b=s[s.y>=2023].n40.dropna()
    if len(b)<20: return None
    r=b.values; pf=r[r>0].sum()/abs(r[r<=0].sum())
    return dict(lab=lab,n=len(s),keep=len(s)/n0*100 if n0 else 100,isr=a.mean(),
                m=r.mean(),md=np.median(r),w=(r>0).mean()*100,pf=pf,
                p5=np.percentile(r,5),mn=r.min())
N0=len(X)
print(f"현행 P1: 전체 {N0:,}건 (학습 {len(X[X.y<=2022])} / 검증 {len(X[X.y>=2023])})\n")
print("## 단일 강화조건 — 건수 감소 vs 안전성\n")
print("| 추가 조건 | 건수 | 보존 | 학습 | **검증** | 중앙값 | 승률 | PF | 하위5% | 최악 |")
print("|---|---|---|---|---|---|---|---|---|---|")
CAND=[("현행",pd.Series(True,index=X.index))]
for q in (5,7,10): CAND.append((f"외국인5일 ≥ {q}%",X.fw5>=q))
for q in (2,3,5): CAND.append((f"외국인60일 ≥ {q}%",X.fw60>=q))
for q in (2,2.5): CAND.append((f"변동성 ≤ {q}%",X.vol20<=q))
for q in (50,80): CAND.append((f"거래량침체 r16 < {q}",X.r16<q))
for q in (80,100): CAND.append((f"단기거래량 rw1 ≤ {q}",X.rw1<=q))
for q in (-5,-3): CAND.append((f"신고가 {q}% 이내",X.fromhi>=q))
for q in (100,200,300): CAND.append((f"거래대금 ≥ {q}억",X.amt20>=q))
for q in (0.5,0.3): CAND.append((f"공매도비중 ≤ {q}%",X.sr20<=q))
for q in (5,0): CAND.append((f"20일수익 ≤ {q}%",X.ret20<=q))
CAND.append(("지수 60일선 위(상승장만)",X.k60))
CAND.append(("지수 20·60일선 위",X.k20&X.k60))
CAND.append(("기관 20일 순매수 ≥ 0",X.ow20>=0))
for q in (30,50): CAND.append((f"저점대비 ≤ +{q}%",X.fromlo<=q))
for nm,m in CAND:
    s=st(X[m.fillna(False)],nm,N0)
    if s: print(f"| {s['lab']} | {s['n']:,} | {s['keep']:.0f}% | {s['isr']:+.2f}% | **{s['m']:+.2f}%** | "
                f"{s['md']:+.2f}% | {s['w']:.0f}% | {s['pf']:.2f} | {s['p5']:.1f}% | {s['mn']:.0f}% |")
