# -*- coding: utf-8 -*-
"""9개 규칙을 전부 켜고 실제 계좌를 굴려본다 (2018~2026).

지금까지는 규칙을 하나씩 따로 쟀다. 실전은 다르다 —
 · 정해둔 종목당 비중·최대 종목수 상한이 있어 신호가 나도 못 사는 날이 있다
 · 현금이 바닥나면 못 산다
 · 여러 규칙이 같은 날 동시에 종목을 요구한다(하락장에 특히)
그래서 '규칙별 평균 수익률'과 '계좌 수익률'은 다른 숫자다. 이걸 잰다.

비교 기준은 코스피 지수(KODEX 200 대용 KS11) 매수후보유.
"""
import io, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent

IX = fdr.DataReader("KS11", "2017-01-01"); IX = IX[IX.Close > 0].copy()
IX["date"] = IX.index.strftime("%Y%m%d")
IX["ma20"] = IX.Close.rolling(20).mean(); IX["ma60"] = IX.Close.rolling(60).mean()
UP20 = dict(zip(IX.date, IX.Close > IX.ma20)); UP60 = dict(zip(IX.date, IX.Close > IX.ma60))

def load(f, mk):
    K = pd.read_pickle(BASE/"data"/f).sort_values(["ticker","date"]).reset_index(drop=True)
    K["pref"] = ~K.ticker.str.endswith("0"); K["mk"] = mk
    g = K.groupby("ticker", sort=False)
    K.loc[K.marcap/1e4 > 2000, "marcap"] = np.nan
    K["cap조"] = K.marcap/1e4
    K["dev25"] = (K.close/g.close.transform(lambda s: s.rolling(25,min_periods=25).mean())-1)*100
    return K
KP = load("kp_ow.pkl","KOSPI"); KQ = load("kq_ow.pkl","KOSDAQ")

# 자사주 공시(P5)
con = sqlite3.connect(BASE/"data"/"dart"/"disclosures.db")
D = pd.read_sql("SELECT stock_code AS ticker, rcept_dt AS dt, report_nm FROM disclosure "
                "WHERE length(stock_code)=6 AND rcept_dt>='20180101' "
                "AND report_nm LIKE '%자기주식취득결정%'", con); con.close()
nm_ = D.report_nm.str.replace(" ","",regex=False)
BB = set(zip(*D[~nm_.str.contains("신탁") & ~nm_.str.contains("정정")][["ticker","dt"]].values.T))
for K in (KP, KQ): K["bb"] = [(t,d) in BB for t,d in zip(K.ticker,K.date)]

# 사이트(index.html)와 조건을 맞추기 위한 보조 피처.
# 이것들이 빠져 있어 백테스트가 실제 규칙보다 느슨했다(audit_rules.py 가 잡아냄).
INS = pd.read_pickle(BASE/"data"/"insider_feat.pkl")[["ticker","date","ins60"]]
for nm in ("KP","KQ"):
    K = {"KP":KP,"KQ":KQ}[nm]
    g = K.groupby("ticker", sort=False)
    K["ret250"] = (K.close/g.close.shift(250)-1)*100                  # 1년 수익률
    ma20 = g.close.transform(lambda s: s.rolling(20).mean())
    K["above20"] = (K.close>ma20).groupby(K.ticker).transform(          # 250일 중 20일선 위 비율(%)
        lambda s: s.rolling(250, min_periods=80).mean())*100
    n0 = len(K)
    K2 = K.merge(INS, on=["ticker","date"], how="left"); assert len(K2)==n0
    K["ins60"] = K2.ins60.values

# [자사주 낙폭](A1) 은 코스피·코스닥 공통 규칙이라 두 패널을 합쳐 쓴다.
# 전체 컬럼을 합치면 메모리가 두 배가 되므로 이 규칙이 쓰는 컬럼만 남긴다.
_C = ["ticker","date","name","close","low","buy","cost","ret60","dil","amt20","bb","mk"]
KB = pd.concat([KP[_C], KQ[_C]], ignore_index=True).sort_values(["ticker","date"]).reset_index(drop=True)
KB["pref"] = ~KB.ticker.str.endswith("0")

def base(K, amt): return ((~K.pref)&(K.close>=1000)&(~K.dil.fillna(False))&(K.amt20.fillna(0)>=amt))
def dn20(K): return K.date.map(UP20).fillna(True) == False
def dn60(K): return K.date.map(UP60).fillna(True) == False
def up60(K): return K.date.map(UP60).fillna(False) == True

RULES = {
 "P1": (KP, 40, 0.15, 12, 7, base(KP,200)&(KP.fromhi>=-10)&(KP.r16<120)&(KP.rw1<=120)&(KP.fw5>=3)
        &(KP.fw60>=1)&(KP.vol20<=2)&(KP.sr20<=0.5)&(KP.ret20<=5)
        &~((KP.above20>70)&(KP.ret250>120))),
 "P2": (KP, 10, None, 15, 2, base(KP,3)&dn20(KP)&(KP.r16<30)&(KP.rw1>=200)&(KP.fw5>=2)
        &(KP.ret3<=-5)&(KP.ret10<=0)&(KP.srd==True)),
 "P3": (KP, 20, None, 5, 3, base(KP,3)&dn60(KP)&(KP.ret20<=-20)&(KP.su1>=1.5)&(KP.fw60>=1)
        &(KP.u<=-10)&(KP.srd==True)),
 "P4": (KP, 5, 0.15, 3, 4, base(KP,10)&dn60(KP)&(KP.u<=-20)&(KP.dma20<=-10)&(KP.mdd60<=-40)&(KP.srd==True)),
 "P5": (KB, 10, None, 5, 3, base(KB,3)&dn60(KB)&KB.bb&(KB.ret60<=-20)),   # 공통(A1)
 "P6": (KP, 5, 0.10, 4, 4, base(KP,10)&dn60(KP)&(KP.dev25<=-25)&(KP.u<=-20)),
 "P7": (KP, 60, None, 4, 5, base(KP,30)&up60(KP)&(KP["cap조"]>=1)&(KP["cap조"]<10)&(KP.fw20>=1)
        &(KP.ow60<0.4)&(KP.r16>=100)&(KP.r16<150)&(KP.fromhi>=-15)&(KP.fromlo>=70)
        &(KP.ins60.fillna(0)>0)),
 "D1": (KQ, 20, None, 5, 3, base(KQ,2)&dn60(KQ)&(KQ.ret20<=-20)&(KQ.su1>=1.5)&(KQ.fw60>=1)
        &(KQ.u<=-20)&(KQ.srd==True)&(KQ.ow20>=0)
        &(KQ['부채비율'].isna()|(KQ['부채비율']<=200))),
 "D2": (KQ, 40, None, 5, 3, base(KQ,5)&dn60(KQ)&(KQ.PBR>0)&(KQ.PBR<=0.5)&(KQ.ret20<=-10)
        &(KQ.su1>=2)&(KQ.u<=-10)&(KQ.ow20>=0)&(KQ.srd==True)),
}
# 신호를 한 표로 모은다 (매수가·청산가·보유중 최저가)
sig = []
for rid,(K,hold,stop,pct,mx,cond) in RULES.items():
    g = K.groupby("ticker", sort=False)
    ex = g.close.shift(-hold)
    lo = g.low.shift(-1).rolling(hold, min_periods=1).min().shift(-(hold-1))
    X = K[cond.fillna(False)].copy()
    X["rid"]=rid; X["hold"]=hold; X["stop"]=stop if stop else np.nan
    X["pct"]=pct; X["mx"]=mx
    X["exit"]=ex.reindex(X.index); X["low"]=lo.reindex(X.index)
    sig.append(X[["date","ticker","name","mk","rid","hold","stop","pct","mx","buy","exit","low","cost"]])
S = pd.concat(sig).dropna(subset=["buy","exit","cost"])
S = S[S.buy > 0]
print(f"전체 신호 {len(S):,}건 (규칙별: " + " ".join(f"{k}:{int(v)}" for k,v in S.rid.value_counts().items()) + ")")

dates = sorted(set(KP.date) | set(KQ.date)); DI = {d:i for i,d in enumerate(dates)}
S["di"] = S.date.map(DI); S = S.sort_values(["di","rid"]).reset_index(drop=True)

def simulate(cash_cap=1.0, scale=1.0, label=""):
    """cash_cap: 총 투입 상한(1.0=계좌 100%) · scale: 종목당 비중 배율"""
    eq = 1.0; open_pos = []; log = []; blocked = 0; taken = 0
    curve = []
    for i, d in enumerate(dates):
        # 만기 청산
        still = []
        for p in open_pos:
            if p["exit_di"] <= i:
                hit = (p["stop"] == p["stop"]) and (p["low"]/p["buy"]-1)*100 <= -p["stop"]*100
                ret = (-p["stop"]*100 - p["cost"]) if hit else ((p["exit"]/p["buy"]-1)*100 - p["cost"])
                eq += p["amt"] * ret/100
                log.append({"rid":p["rid"],"date":p["date"],"ret":ret,"amt":p["amt"]})
            else: still.append(p)
        open_pos = still
        # 신규 진입
        todays = S[S.di == i]
        if len(todays):
            invested = sum(p["amt"] for p in open_pos)
            for t in todays.itertuples():
                n_rule = sum(1 for p in open_pos if p["rid"]==t.rid)
                w = eq * t.pct/100 * scale
                if n_rule >= t.mx or invested + w > eq*cash_cap or any(
                        p["ticker"]==t.ticker for p in open_pos):
                    blocked += 1; continue
                open_pos.append(dict(rid=t.rid,ticker=t.ticker,date=t.date,buy=t.buy,exit=t.exit,
                                     low=t.low,cost=t.cost,stop=t.stop,amt=w,exit_di=i+t.hold))
                invested += w; taken += 1
        curve.append((d, eq, sum(p["amt"] for p in open_pos)/eq if eq>0 else 0))
    C = pd.DataFrame(curve, columns=["date","nav","expo"])
    L = pd.DataFrame(log)
    yrs = (len(dates))/252
    cagr = (C.nav.iloc[-1])**(1/yrs) - 1
    mdd = ((C.nav/C.nav.cummax()) - 1).min()*100
    print(f"  {label:<22} 최종 {C.nav.iloc[-1]:>6.2f}배 · 연 {cagr*100:>6.2f}% · 최대낙폭 {mdd:>6.1f}% "
          f"· 거래 {taken:>5}건(막힘 {blocked:>5}) · 평균노출 {C.expo.mean()*100:>4.0f}%")
    return C, L

print(f"\n## 계좌 시뮬레이션 (2018~2026, {len(dates)}거래일)")
C, L = simulate(1.0, 1.0, "설정 그대로")
simulate(1.0, 0.5, "비중 절반")
simulate(0.5, 1.0, "총투입 50% 상한")

kk = IX[(IX.date>=dates[0]) & (IX.date<=dates[-1])]
bh = kk.Close.iloc[-1]/kk.Close.iloc[0]
yrs = len(dates)/252
print(f"\n  {'코스피 매수후보유':<22} 최종 {bh:>6.2f}배 · 연 {(bh**(1/yrs)-1)*100:>6.2f}% "
      f"· 최대낙폭 {((kk.Close/kk.Close.cummax())-1).min()*100:>6.1f}%")

print(f"\n## 규칙별 실제 기여 (설정 그대로)")
print(f"  {'규칙':<4} {'체결':>5} {'평균%':>7} {'승률':>5} {'총기여(계좌%p)':>14}")
for rid in ["P1","P2","P3","P4","P5","P6","P7","D1","D2"]:
    z = L[L.rid==rid]
    if not len(z): print(f"  {rid:<4} {0:>5}"); continue
    print(f"  {rid:<4} {len(z):>5} {z.ret.mean():>7.2f} {(z.ret>0).mean():>4.0%} "
          f"{(z.amt*z.ret/100).sum()*100:>13.1f}")
print(f"\n## 연도별 계좌")
C["yr"]=C.date.str[:4]
for y,gv in C.groupby("yr"):
    print(f"  {y}: {(gv.nav.iloc[-1]/gv.nav.iloc[0]-1)*100:>+7.2f}%  (평균 노출 {gv.expo.mean()*100:>3.0f}%)")
