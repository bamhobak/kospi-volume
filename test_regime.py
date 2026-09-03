# -*- coding: utf-8 -*-
"""국면별 성적 — 횡보장에서 규칙이 지는가.

2016~2017 은 표본이 42건뿐이라 결론을 낼 수 없다. 대신 전 기간(2016~2026)을
국면으로 갈라 재면 표본이 충분해진다. 국면은 코스피의 60일선 이격으로 나눈다
(기존 분석과 같은 정의):  상승 >+5% · 횡보 -5~+5% · 하락 <-5%

주의: 규칙 대부분이 '코스피 60일선 아래' 를 게이트로 쓴다. 그래서 상승 국면에는
애초에 열리지 않는다. 횡보 국면은 게이트를 통과하는 날이 섞여 있어 신호가 난다.
사용: python test_regime.py
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd, FinanceDataReader as fdr
BASE = Path(__file__).parent
parts = [fdr.DataReader("KS11", a, b) for a, b in
         (("2015-01-01","2019-12-31"), ("2020-01-01","2026-09-03"))]
IX = pd.concat(parts); IX = IX[~IX.index.duplicated()].sort_index(); IX = IX[IX.Close > 0]
IX["d"] = IX.index.strftime("%Y%m%d")
IX["ma60"] = IX.Close.rolling(60).mean()
IX["dev"] = (IX.Close/IX.ma60 - 1)*100
REG = dict(zip(IX.d, np.where(IX.dev > 5, "상승", np.where(IX.dev < -5, "하락", "횡보"))))
UP60 = dict(zip(IX.d, IX.Close > IX.ma60)); UP20 = dict(zip(IX.d, IX.Close > IX.Close.rolling(20).mean()))
print("  국면별 거래일 수: " + " · ".join(
    f"{k} {v}일({v/len(IX)*100:.0f}%)" for k,v in pd.Series(list(REG.values())).value_counts().items()))

def load(f):
    K = pd.read_pickle(BASE/"data"/f).sort_values(["ticker","date"]).reset_index(drop=True)
    K["pref"] = ~K.ticker.str.endswith("0")
    K["up60"] = K.date.map(UP60).fillna(False); K["up20"] = K.date.map(UP20).fillna(False)
    g = K.groupby("ticker", sort=False)
    K["dev25"] = (K.close/g.close.transform(lambda s: s.rolling(25,min_periods=25).mean())-1)*100
    K["cap조"] = K.marcap/1e12
    K["reg"] = K.date.map(REG)
    return K
KP, KQ = load("panel_kp.pkl"), load("panel_kq.pkl")
KB = pd.concat([KP,KQ], ignore_index=True).sort_values(["ticker","date"]).reset_index(drop=True)
def base(K,a): return (~K.pref)&(~K.dil.fillna(False))&(K.close>=1000)&(K.amt20>=a)
R = {
 "외인 매집":   (KP,60,None, base(KP,30)&KP.up60&(KP["cap조"]>=1)&(KP["cap조"]<10)&(KP.fw20>=1)
                &(KP.ow60<0.4)&(KP.r16>=100)&(KP.r16<150)&(KP.fromhi>=-15)&(KP.fromlo>=70)&(KP.ins60.fillna(0)>0)),
 "조용한 신고가":(KP,40,0.15, base(KP,200)&(KP.fromhi>=-10)&(KP.r16<120)&(KP.rw1<=120)&(KP.fw5>=3)
                &(KP.fw60>=1)&(KP.vol20<=2)&(KP.sr20<=0.5)&(KP.ret20<=5)),
 "업종붕괴 이탈":(KP,5,0.15, base(KP,10)&(~KP.up60)&(KP.u<=-20)&(KP.dma20<=-10)&(KP.mdd60<=-40)&(KP.srd==True)),
 "깊은 이격":  (KP,5,0.10, base(KP,10)&(~KP.up60)&(KP.dev25<=-25)&(KP.u<=-20)),
 "폭락반등":   (KP,20,None, base(KP,3)&(~KP.up60)&(KP.ret20<=-20)&(KP.su1>=1.5)&(KP.fw60>=1)&(KP.u<=-10)&(KP.srd==True)),
 "조정매집":   (KP,10,None, base(KP,3)&(~KP.up20)&(KP.r16<30)&(KP.rw1>=200)&(KP.fw5>=2)&(KP.ret3<=-5)&(KP.ret10<=0)&(KP.srd==True)),
 "낙폭과대":   (KQ,20,None, base(KQ,2)&(~KQ.up60)&(KQ.ret20<=-20)&(KQ.su1>=1.5)&(KQ.fw60>=1)&(KQ.u<=-20)&(KQ.srd==True)&(KQ.ow20>=0)),
 "자사주 낙폭": (KB,10,None, base(KB,3)&(KB.bb==True)&(KB.ret60<=-20)&(~KB.up60)),
}
def trades(K,hold,stop,cond):
    g=K.groupby("ticker",sort=False); col=f"n{hold}"
    if stop:
        low=pd.concat([g.low.shift(-i) for i in range(hold)],axis=1).min(axis=1)
        r=np.where((low<=K.buy*(1-stop)).fillna(False),-stop*100-K.cost,K[col])
    else: r=K[col].values
    m=cond.fillna(False)
    X=K[m].copy(); X["_r"]=r[m.values]; X=X.dropna(subset=["_r"])
    d=sorted(K.date.unique()); di={x:i for i,x in enumerate(d)}
    X["di"]=X.date.map(di); X=X.sort_values("di")
    keep,last=[],{}
    for t,i,ix in zip(X.ticker.values,X.di.values,X.index):
        if last.get(t,-10**9)>=i: continue
        last[t]=i+hold; keep.append(ix)
    return X.loc[keep]
print(f"\n  {'규칙':<15}{'하락 국면':>22}{'횡보 국면':>22}{'상승 국면':>22}")
print("  "+"-"*81)
TOT={}
for nm,(K,hold,stop,cond) in R.items():
    Z=trades(K,hold,stop,cond); cells=""
    for rg in ("하락","횡보","상승"):
        S=Z[Z.reg==rg]
        if len(S)>=5:
            v=S._r.to_numpy()
            cells+=f"{len(S):>6}건{v.mean():>+7.2f}%승{(v>0).mean()*100:>3.0f}%"
            TOT.setdefault(rg,[]).append(v)
        else: cells+=f"{('('+str(len(S))+'건)') if len(S) else '없음':>20}"
    print(f"  {nm:<15}{cells}")
print("  "+"-"*81)
for rg in ("하락","횡보","상승"):
    if rg in TOT:
        v=np.concatenate(TOT[rg])
        print(f"  전체 {rg} 국면: {len(v):,}건 · 평균 {v.mean():+.2f}% · 승률 {(v>0).mean()*100:.0f}% · 중앙 {np.median(v):+.2f}%")
