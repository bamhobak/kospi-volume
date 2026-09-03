# -*- coding: utf-8 -*-
"""2016~2017 구간만 제대로 측정 — 신호가 0건인 게 진짜인지 조건별로 분해한다.

앞선 측정에서 [업종붕괴 이탈]·[깊은 이격]이 0건이었다. 그게 정말 시장에 그런
상황이 없어서인지, 아니면 데이터 결측(업종 2016년 35% 미상) 때문에 걸러진 것인지
구분해야 한다. 조건을 하나씩 얹으며 남는 행 수를 세면 어디서 끊기는지 보인다.
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd, FinanceDataReader as fdr
BASE = Path(__file__).parent
parts=[fdr.DataReader("KS11",a,b) for a,b in (("2015-01-01","2019-12-31"),("2020-01-01","2026-09-03"))]
IX=pd.concat(parts); IX=IX[~IX.index.duplicated()].sort_index(); IX=IX[IX.Close>0]
IX["d"]=IX.index.strftime("%Y%m%d")
UP60=dict(zip(IX.d, IX.Close>IX.Close.rolling(60).mean()))
UP20=dict(zip(IX.d, IX.Close>IX.Close.rolling(20).mean()))
def load(f):
    K=pd.read_pickle(BASE/"data"/f)
    K=K[(K.date>="20160101")&(K.date<="20171231")].sort_values(["ticker","date"]).reset_index(drop=True)
    K["pref"]=~K.ticker.str.endswith("0")
    K["up60"]=K.date.map(UP60).fillna(False); K["up20"]=K.date.map(UP20).fillna(False)
    g=K.groupby("ticker",sort=False)
    K["dev25"]=(K.close/g.close.transform(lambda s:s.rolling(25,min_periods=25).mean())-1)*100
    K["cap조"]=K.marcap/1e12
    return K
KP,KQ=load("panel_kp.pkl"),load("panel_kq.pkl")
print(f"  2016~2017 패널: 코스피 {len(KP):,}행({KP.ticker.nunique()}종목) · "
      f"코스닥 {len(KQ):,}행({KQ.ticker.nunique()}종목)\n")

def steps(nm, K, conds):
    print(f"  [{nm}] — 조건을 하나씩 얹었을 때 남는 행")
    m = pd.Series(True, index=K.index)
    for label, c in conds:
        m = m & c.fillna(False)
        n = int(m.sum())
        bar = "█"*min(30, int(np.log10(n+1)*8))
        print(f"     {label:<28}{n:>9,}  {bar}")
        if n == 0:
            print(f"     └ 여기서 끊겼다"); break
    print()

steps("업종붕괴 이탈", KP, [
    ("전체", pd.Series(True,index=KP.index)),
    ("+ 보통주·희석공시 없음", (~KP.pref)&(~KP.dil.fillna(False))),
    ("+ 주가 ≥1,000원", KP.close>=1000),
    ("+ 거래대금 ≥10억", KP.amt20>=10),
    ("+ 코스피 60일선 아래", ~KP.up60),
    ("+ 업종 60일 ≤-20%", KP.u<=-20),
    ("+ 20일선 이격 ≤-10%", KP.dma20<=-10),
    ("+ 60일 최대낙폭 ≤-40%", KP.mdd60<=-40),
    ("+ 공매도 감소", KP.srd==True)])
steps("깊은 이격", KP, [
    ("전체", pd.Series(True,index=KP.index)),
    ("+ 보통주·희석공시 없음", (~KP.pref)&(~KP.dil.fillna(False))),
    ("+ 주가 ≥1,000원 · 거래대금 ≥10억", (KP.close>=1000)&(KP.amt20>=10)),
    ("+ 코스피 60일선 아래", ~KP.up60),
    ("+ 25일선 이격 ≤-25%", KP.dev25<=-25),
    ("+ 업종 60일 ≤-20%", KP.u<=-20)])
steps("조용한 신고가", KP, [
    ("전체", pd.Series(True,index=KP.index)),
    ("+ 보통주·희석 없음·주가·거래대금 ≥200억", (~KP.pref)&(~KP.dil.fillna(False))&(KP.close>=1000)&(KP.amt20>=200)),
    ("+ 52주 고점 -10% 이내", KP.fromhi>=-10),
    ("+ 거래량 침체(2M/1Y<120%)", KP.r16<120),
    ("+ 단기 거래량 조용(3D/2M≤120%)", KP.rw1<=120),
    ("+ 외인 5일 ≥3%", KP.fw5>=3),
    ("+ 외인 60일 ≥1%", KP.fw60>=1),
    ("+ 변동성 ≤2%", KP.vol20<=2),
    ("+ 공매도 ≤0.5%", KP.sr20<=0.5),
    ("+ 20일 상승 ≤5%", KP.ret20<=5)])
print("  ── 참고: 그 구간에 극단적 낙폭 종목이 있었나 ──")
for c,lab in ((KP.mdd60<=-40,"60일 최대낙폭 ≤-40%"),(KP.dev25<=-25,"25일선 이격 ≤-25%"),
              (KP.u<=-20,"업종 60일 ≤-20%"),(KP.ret20<=-20,"20일 수익률 ≤-20%")):
    s=c.fillna(False)
    print(f"     {lab:<24} {int(s.sum()):>7,}행 · 종목 {KP[s].ticker.nunique():>4}개 · "
          f"해당일 {KP[s].date.nunique():>4}일")
