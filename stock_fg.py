# -*- coding: utf-8 -*-
"""종목별 공포·탐욕 지수 — 코스피 지수용(collect_feargreed.py)을 종목 단위로 옮긴다.

지수용 여섯 재료 중 시장 폭(breadth)·채권 지표 셋은 종목에 없다. 종목이 가진 것으로 바꾼다.
  변동성 .30  20일 실현변동성(vol20)         높으면 공포 → 100-백분위
  모멘텀 .25  120일선 이격(dma120)           높으면 탐욕 → 백분위
  강도  .15  250일 고저 범위 안 위치         고점 근처면 탐욕 → 위치×100
  추세  .15  20일 중 상승일 비율(above20)    높으면 탐욕 → 백분위
  위험  .10  신용잔고 20일 변화(cr_chg20)·공매도비중(sr20)  빚이 늘고 공매도가 줄면 탐욕
  안전  .05  외국인+기관 20일 순매수(fw20+ow20)  큰손이 사면 탐욕
백분위는 '그 종목의 지금까지 과거' 대비(expanding, 최소 250일) — 미래를 안 본다. 없는 재료는 가중치를 재배분.
산출: data/stock_fg_{kp,kq}.pkl (ticker, date, fg, 여섯 성분)
사용: python stock_fg.py [--market kp|kq]
"""
import io, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
arg = lambda k, d: sys.argv[sys.argv.index(k)+1] if k in sys.argv else d
MK = [arg("--market", None)] if "--market" in sys.argv else ["kp", "kq"]
W = {"volatility":0.30, "momentum":0.25, "strength":0.15, "trend":0.15, "risk":0.10, "safe":0.05}
t0 = time.time(); say = lambda m: print(f"[{(time.time()-t0)/60:5.1f}분] {m}", flush=True)

def pct_exp(g, col, minp=250):
    """종목별 확장창 백분위(0~100). 오늘 값이 자기 과거 중 어디쯤인가."""
    return g[col].transform(lambda s: s.expanding(min_periods=minp).rank(pct=True))*100

for mk in MK:
    say(f"── {mk.upper()} 패널 로드")
    cols = ["ticker","date","close","vol20","dma120","fromhi","fromlo","sr20","fw20","ow20"]
    K = pd.read_pickle(BASE/"data"/f"panel_{mk}.pkl")
    K = K[[c for c in cols if c in K.columns]].sort_values(["ticker","date"]).reset_index(drop=True)
    say(f"  {len(K):,}행 · 열 {list(K.columns)}")
    g = K.groupby("ticker", sort=False)
    # 패널에 없는 두 재료는 portfolio.py 와 같은 방식으로 여기서 만든다.
    #  · 추세: 최근 20일 중 상승일 비율
    #  · 신용잔고 20일 변화: data/kis/market.db 의 credit(loan_rmnd)
    K["above20"] = (g.close.transform(lambda s: (s > s.shift(1)).rolling(20).mean())*100)
    import sqlite3
    _cc = sqlite3.connect(f"file:{BASE}/data/kis/market.db?mode=ro", uri=True, timeout=600)
    _CR = pd.read_sql("SELECT date,ticker,loan_rmnd FROM credit", _cc); _cc.close()
    _CR = _CR.sort_values(["ticker","date"])
    _CR["cr_chg20"] = (_CR.loan_rmnd/_CR.groupby("ticker",sort=False).loan_rmnd.shift(20)-1)*100
    K["cr_chg20"] = K.merge(_CR[["date","ticker","cr_chg20"]], on=["ticker","date"], how="left").cr_chg20.values
    del _CR
    g = K.groupby("ticker", sort=False)
    say(f"  추세·신용 재료 생성 (신용 보유율 {K.cr_chg20.notna().mean()*100:.0f}%)")
    C = pd.DataFrame(index=K.index)
    C["volatility"] = 100 - pct_exp(g, "vol20");                 say("  변동성")
    C["momentum"]   = pct_exp(g, "dma120");                      say("  모멘텀")
    # 강도: 250일 범위 안 위치. fromhi=c/hi-1(≤0), fromlo=c/lo-1(≥0) → (c-lo)/(hi-lo)
    hi_lo = (1+K.fromlo)/(1+K.fromhi)                             # hi/lo
    pos = (K.fromlo/(hi_lo-1)).where(hi_lo > 1.0001)
    C["strength"]   = (pos.clip(0,1)*100);                        say("  강도")
    C["trend"]      = pct_exp(g, "above20");                     say("  추세")
    r1 = pct_exp(g, "cr_chg20") if "cr_chg20" in K else None
    r2 = (100 - pct_exp(g, "sr20")) if "sr20" in K else None
    C["risk"] = pd.concat([x for x in (r1, r2) if x is not None], axis=1).mean(axis=1) if (r1 is not None or r2 is not None) else np.nan
    say("  위험")
    K["_flow"] = K.fw20.fillna(0) + K.ow20.fillna(0)
    g = K.groupby("ticker", sort=False)
    C["safe"]       = pct_exp(g, "_flow");                       say("  안전")
    # 가중 평균 — 결측 성분은 빼고 가중치 재배분
    num = sum(C[k].fillna(0)*w for k, w in W.items())
    den = sum(C[k].notna()*w for k, w in W.items())
    fg = (num/den).where(den >= 0.5)                              # 재료 절반 미만이면 점수 없음
    out = pd.DataFrame({"ticker": K.ticker, "date": K.date, "fg": fg.astype("float32")})
    for k in W: out[k] = C[k].astype("float32")
    out.to_pickle(BASE/"data"/f"stock_fg_{mk}.pkl")
    say(f"  저장 stock_fg_{mk}.pkl · 점수 있는 행 {fg.notna().mean()*100:.0f}%")
    v = fg.dropna()
    print(f"  분포: 5% {v.quantile(.05):.0f} · 25% {v.quantile(.25):.0f} · 중앙 {v.median():.0f} · 75% {v.quantile(.75):.0f} · 95% {v.quantile(.95):.0f}")
    # 극단 종목 예시 — 최근일
    last = out[out.date == out.date.max()].dropna(subset=["fg"]).merge(K[["ticker","date","close"]], on=["ticker","date"])
    nm = pd.read_pickle(BASE/"data"/f"panel_{mk}.pkl", ) if False else None
    print(f"  최근일 {out.date.max()} 극단 공포 5: " + ", ".join(f"{r.ticker}({r.fg:.0f})" for r in last.nsmallest(5,'fg').itertuples()))
    print(f"  최근일 극단 탐욕 5: " + ", ".join(f"{r.ticker}({r.fg:.0f})" for r in last.nlargest(5,'fg').itertuples()))
    del K, C, g, out
say("완료")
