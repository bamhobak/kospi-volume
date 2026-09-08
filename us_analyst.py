# -*- coding: utf-8 -*-
"""미국에만 있는 축 수집 — 애널리스트 등급변경 · 실적 서프라이즈.

한국 규칙을 그대로 옮기는 건 실패했다(`us_acct.py`). 그러면 반대로 미국에만 있는
재료로 미국용 축을 찾아야 한다. 한국에 없거나 훨씬 부실한 것 둘을 받는다.

  ① 등급 변경(upgrades_downgrades) — 2012~, 종목당 수백 건.
     Firm·ToGrade·FromGrade·Action·목표가(현재/직전) 까지 온다.
     **우리 역발상 스타일과 잘 맞는다** — "모두가 하향한 뒤에 산다" 를 잴 수 있다.
     한국은 커버리지가 얇고 이 데이터가 유료다.
  ② 실적 서프라이즈(earnings_dates) — 2014~ 분기별. 추정 EPS·실제 EPS·서프라이즈%.
     PEAD(실적발표 후 표류)는 금융에서 가장 오래 살아남은 이상현상 중 하나다.
     한국은 발표일이 들쭉날쭉하고 컨센서스가 유료다.

조각 단위로 저장하고 이미 받은 조각은 건너뛴다(재개 가능). 6,085종목 약 165분.
"""
import io, sys, time, json, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import pandas as pd, yfinance as yf
US=Path("data/us"); OUT=US/"analyst"; OUT.mkdir(parents=True, exist_ok=True)
CH=200
def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
syms=pd.read_csv(US/"tickers.csv",dtype=str).Symbol.tolist()
chunks=[syms[i:i+CH] for i in range(0,len(syms),CH)]
log(f"종목 {len(syms):,}개 · 조각 {len(chunks)}개")
t0=time.time(); ne=nu=0
for i,c in enumerate(chunks):
    pe, pu = OUT/f"earn_{i:03d}.pkl", OUT/f"upg_{i:03d}.pkl"
    if pe.exists() and pu.exists(): continue
    E=[]; U=[]
    for s in c:
        T=yf.Ticker(s)
        try:
            d=T.get_earnings_dates(limit=100)
            if d is not None and len(d):
                d=d.reset_index(); d.columns=[str(x) for x in d.columns]
                d["ticker"]=s; E.append(d)
        except Exception: pass
        try:
            u=T.upgrades_downgrades
            if u is not None and len(u):
                u=u.reset_index(); u.columns=[str(x) for x in u.columns]
                u["ticker"]=s; U.append(u)
        except Exception: pass
    if E: pd.concat(E,ignore_index=True).to_pickle(pe); ne+=len(E)
    else: pd.DataFrame().to_pickle(pe)
    if U: pd.concat(U,ignore_index=True).to_pickle(pu); nu+=len(U)
    else: pd.DataFrame().to_pickle(pu)
    el=time.time()-t0
    log(f"  조각 {i:>2}/{len(chunks)-1} · 실적 {len(E):>3}종목 · 등급 {len(U):>3}종목 · "
        f"남은시간 약 {(len(chunks)-i-1)*el/(i+1)/60:.0f}분")
log(f"끝. 실적 {ne:,}종목 · 등급 {nu:,}종목 → {OUT}")
