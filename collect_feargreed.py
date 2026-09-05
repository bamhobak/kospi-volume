# -*- coding: utf-8 -*-
"""코스피·코스닥 공포탐욕지수(Fear & Greed Index) 2005~현재 산출·저장.

⚠ 먼저 알아둘 것: 한국 시장에는 2005년까지 거슬러 받을 수 있는 공포탐욕지수 시계열이 없다.
   · CNN Fear & Greed 는 미국 전용이다.
   · 국내 공식 '공포지수' 인 VKOSPI 는 2009-04-13 부터 산출된다(그 이전은 존재하지 않는다).
   · feargreed.co.kr 등 국내 사이트는 실시간 계산만 하고 과거 이력은 2026-03 부터뿐이며 공개 API 도 없다.
   그래서 **가장 대중적인 방식(CNN 방법론 · feargreed.co.kr 이 공개한 가중치)을 우리 데이터로 재현**해
   2005년까지 소급 산출한다. 남의 숫자를 긁어오는 것보다 재현 가능하고 백테스트에 바로 쓸 수 있다.

구성 요소(0~100 정규화 후 가중합, feargreed.co.kr 공개 가중치에 맞춤)
  변동성   30%  **VKOSPI 전 구간 시계열**(collect_vkospi.py 가 만든 data/vkospi.csv)의 역방향.
                2013-08~ 은 실측, 그 이전은 HAR 추정(검증 상관 0.928·절대오차 4.13).
                ⚠ 이 요소만은 **확장창 백분위**(과거 전체 대비)로 정규화한다. 3년 롤링 백분위를
                쓰면 최근 3년이 계속 험할 때 VKOSPI 39 가 "24" 로 읽혀 수준이 사라진다
                (2026-09 에 실제로 그랬다). 나머지 요소는 3년 롤링 그대로다.
  모멘텀   25%  지수 종가 / 125일 이동평균 (CNN 과 동일)
  주가강도 15%  52주 신고가 종목수 − 신저가 종목수, 유효 종목수 대비
  추세     15%  지수의 20일 수익률
  위험선호 10%  코스닥 20일 − 코스피 20일 수익률 (위험자산 선호도)
  안전자산  5%  지수 20일 수익률 − 원/달러 20일 상승률 (원화 약세 = 위험회피)
  ※ 참고로 '시장 폭(breadth)' 도 함께 계산해 저장한다(상승·하락 종목 거래량 차이, 가중치 0).

정규화: 각 요소를 750거래일(약 3년) 롤링 백분위로 0~100 (초기 구간은 확장창, 최소 250일).
출력: data/feargreed.db 테이블 feargreed + data/feargreed.csv
사용: python collect_feargreed.py [--rebuild]
"""
import sqlite3, sys, time
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

BASE = Path(__file__).parent
DB = BASE / "data" / "feargreed.db"
OUT = BASE / "data" / "feargreed.csv"
START = "2005-01-01"
t0 = time.time()
def log(m): print(f"[{(time.time()-t0)/60:5.1f}분] {m}", flush=True)

# ── 1) 지수·환율 ────────────────────────────────────────────────
log("지수·환율 받는 중")
def idx(code):
    d = fdr.DataReader(code, START)
    d = d[d.Close > 0].copy()
    d.index = pd.to_datetime(d.index)
    return d.Close.rename(code)
KS = idx("KS11"); KQ = idx("KQ11")
FX = idx("USD/KRW")
# ⚠ 원/달러는 주말·공휴일에도 값이 있다. 그대로 합치고 ffill 하면 휴장일이 거래일로 둔갑한다
#   (예전에 893일이 그렇게 섞여 있었다). 코스피가 실제로 거래된 날로 먼저 자른다.
IX = pd.concat([KS, KQ, FX], axis=1).sort_index()
IX = IX.loc[KS.index].ffill().dropna(subset=["KS11", "KQ11"])
IX["d"] = IX.index.strftime("%Y%m%d")
log(f"지수 {len(IX)}거래일 {IX.d.iloc[0]}~{IX.d.iloc[-1]}")

# ── 2) 종목 단위(신고가·신저가·상승하락 거래량) ─────────────────
def stocks(market):
    """2005~ 전 구간. kospi.db 는 백필로 두 시장을 다 담고, 2018+ 코스닥은 kosdaq.db 에 있다."""
    fr = []
    c = sqlite3.connect(f"file:{BASE}/data/kospi.db?mode=ro", uri=True, timeout=600)
    if market == "KOSPI":
        q = ("SELECT date,ticker,close,volume FROM daily "
             "WHERE (market='KOSPI' OR market IS NULL) AND close>0")
    else:
        q = "SELECT date,ticker,close,volume FROM daily WHERE market='KOSDAQ' AND close>0"
    fr.append(pd.read_sql(q, c)); c.close()
    if market == "KOSDAQ":
        k = sqlite3.connect(f"file:{BASE}/data/kosdaq.db?mode=ro", uri=True, timeout=600)
        fr.append(pd.read_sql("SELECT date,ticker,close,volume FROM daily WHERE close>0", k)); k.close()
    S = pd.concat(fr, ignore_index=True).drop_duplicates(["ticker", "date"])
    return S.sort_values(["ticker", "date"])

def breadth(market):
    S = stocks(market)
    log(f"  {market} 종목 데이터 {len(S):,}행 {S.date.min()}~{S.date.max()}")
    g = S.groupby("ticker", sort=False)
    hi = g.close.transform(lambda s: s.rolling(250, min_periods=120).max())
    lo = g.close.transform(lambda s: s.rolling(250, min_periods=120).min())
    S["nh"] = (S.close >= hi * 0.999).astype(float)
    S["nl"] = (S.close <= lo * 1.001).astype(float)
    S["chg"] = g.close.diff()
    S["upv"] = np.where(S.chg > 0, S.volume, 0.0)
    S["dnv"] = np.where(S.chg < 0, S.volume, 0.0)
    S["valid"] = hi.notna().astype(float)
    D = S.groupby("date").agg(nh=("nh", "sum"), nl=("nl", "sum"), valid=("valid", "sum"),
                              upv=("upv", "sum"), dnv=("dnv", "sum"))
    D["strength"] = (D.nh - D.nl) / D.valid.replace(0, np.nan) * 100
    D["bread"] = (D.upv - D.dnv) / (D.upv + D.dnv).replace(0, np.nan) * 100
    D["bread20"] = D.bread.rolling(20, min_periods=15).mean()
    return D[["strength", "bread20", "nh", "nl", "valid"]]

log("종목 단위 집계")
B = {m: breadth(m) for m in ("KOSPI", "KOSDAQ")}

# ── 3) 요소 계산 ────────────────────────────────────────────────
def pctile(s, win=750, minp=250):
    """롤링 백분위(0~100). 값이 과거 창에서 어느 위치인가."""
    return s.rolling(win, min_periods=minp).apply(
        lambda x: (x[:-1] < x[-1]).mean() * 100 if len(x) > 1 else np.nan, raw=True)

# VKOSPI — 있으면 변동성 요소를 이걸로 쓴다(없던 구간은 실현변동성을 회귀로 맞춰 잇는다)
def vkospi():
    f = BASE/"data"/"vkospi.csv"
    if not f.exists():
        log("⚠ data/vkospi.csv 없음 — 실현변동성만 쓴다 (collect_vkospi.py 를 먼저 돌릴 것)")
        return None
    V = pd.read_csv(f, dtype={"date": str})
    n = int((V.src == "실측").sum()) if "src" in V.columns else len(V)
    log(f"VKOSPI 시계열 {len(V):,}일 (실측 {n:,} · 추정 {len(V)-n:,})")
    return dict(zip(V.date, V.close))

def pct_exp(s, minp=500):
    """확장창 백분위 — 오늘 값이 '지금까지의 모든 과거' 중 어디쯤인가(미래를 안 본다)."""
    return s.rolling(len(s), min_periods=minp).apply(
        lambda x: (x[:-1] < x[-1]).mean() * 100 if len(x) > 1 else np.nan, raw=True)
VK = vkospi()

def build(market):
    px = IX["KS11"] if market == "KOSPI" else IX["KQ11"]
    F = pd.DataFrame(index=IX.index); F["date"] = IX.d
    ret1 = px.pct_change()
    F["vol20"] = ret1.rolling(20).std() * np.sqrt(252) * 100        # 실현변동성(연율 %)
    F["mom"] = px / px.rolling(125).mean() * 100 - 100              # 125일선 이격
    F["trend"] = px.pct_change(20) * 100                            # 20일 수익률
    F["risk"] = IX.KQ11.pct_change(20)*100 - IX.KS11.pct_change(20)*100
    F["safe"] = px.pct_change(20)*100 - IX["USD/KRW"].pct_change(20)*100
    bb = B[market].reindex(IX.d.values)
    F["strength"] = bb.strength.values
    F["bread"] = bb.bread20.values
    F["nh"] = bb.nh.values; F["nl"] = bb.nl.values
    # 변동성 원천 = VKOSPI 전 구간 시계열(실측 + 소급 추정)
    F["vk"] = F.date.map(VK) if VK else np.nan
    F["volsrc"] = F.vk.where(F.vk.notna(), F.vol20)
    # 0~100 정규화 — 변동성은 높을수록 공포이므로 뒤집는다.
    # 변동성만 확장창(수준 유지), 나머지는 3년 롤링(국면 상대평가).
    N = pd.DataFrame(index=F.index)
    N["volatility"] = 100 - pct_exp(F.volsrc)
    N["volatility_rv"] = 100 - pctile(F.volsrc)   # 참고: 예전 방식(3년 롤링)
    N["momentum"]   = pctile(F.mom)
    N["strength"]   = pctile(F.strength)
    N["trend"]      = pctile(F.trend)
    N["risk"]       = pctile(F.risk)
    N["safe"]       = pctile(F.safe)
    N["breadth"]    = pctile(F.bread)
    W = {"volatility":0.30, "momentum":0.25, "strength":0.15, "trend":0.15, "risk":0.10, "safe":0.05}
    num = sum(N[k].fillna(0)*w for k, w in W.items())
    den = sum(N[k].notna()*w for k, w in W.items())
    N["score"] = (num / den.replace(0, np.nan)).round(1)
    # 비교용 — 변동성 요소만 실현변동성으로 바꾼 점수
    Wr = dict(W); N2 = N.rename(columns={"volatility_rv": "volatility"})
    num2 = sum(N2[k].fillna(0)*w for k, w in Wr.items() if k != "volatility") + N["volatility_rv"].fillna(0)*W["volatility"]
    den2 = sum(N2[k].notna()*w for k, w in Wr.items() if k != "volatility") + N["volatility_rv"].notna()*W["volatility"]
    N["score_rv"] = (num2 / den2.replace(0, np.nan)).round(1)
    N["market"] = market; N["date"] = F.date
    for c in ("vol20","volsrc","vk","mom","trend","risk","safe","strength","bread","nh","nl"): N["raw_"+c] = F[c]
    # 종목 집계(강도)가 없는 날은 점수를 내지 않는다 — 증분 갱신기(update_feargreed.py)와 기준을 맞춘다.
    return N.dropna(subset=["score", "raw_strength"])

log("요소 계산·정규화")
R = pd.concat([build(m) for m in ("KOSPI", "KOSDAQ")], ignore_index=True)
cols = (["date","market","score","score_rv","volatility","volatility_rv","momentum","strength","trend","risk","safe","breadth"]
        + [c for c in R.columns if c.startswith("raw_")])
R = R[cols].sort_values(["market","date"])
for c in R.columns:
    if c not in ("date","market"): R[c] = R[c].astype(float).round(3)

con = sqlite3.connect(DB)
con.execute("DROP TABLE IF EXISTS feargreed")
con.execute("CREATE TABLE feargreed(date TEXT, market TEXT, score REAL, score_rv REAL, "
            "volatility REAL, volatility_rv REAL, momentum REAL, strength REAL, trend REAL, risk REAL, safe REAL, breadth REAL, "
            + ",".join(f"{c} REAL" for c in R.columns if c.startswith("raw_")) + ", PRIMARY KEY(date,market))")
ph = ",".join("?"*len(R.columns))
con.executemany(f"INSERT OR REPLACE INTO feargreed VALUES({ph})", R.itertuples(index=False, name=None))
con.commit(); con.close()
R.to_csv(OUT, index=False, encoding="utf-8-sig")

def band(v):
    return ("극단적 공포" if v < 25 else "공포" if v < 45 else "중립" if v < 55
            else "탐욕" if v < 75 else "극단적 탐욕")
print()
for m in ("KOSPI", "KOSDAQ"):
    X = R[R.market == m]
    print(f"■ {m}  {len(X):,}일  {X.date.min()}~{X.date.max()}  평균 {X.score.mean():.1f}")
    last = X.iloc[-1]
    d = (X.score - X.score_rv).dropna()
    print(f"   변동성 정규화 확장창 적용 · 예전(3년 롤링) 대비 점수 평균 {d.mean():+.2f} 이동 (최대 {d.abs().max():.1f})")
    print(f"   최신 {last.date}: {last.score:.1f} ({band(last.score)}) · "
          f"변동성 {last.volatility:.0f} 모멘텀 {last.momentum:.0f} 강도 {last.strength:.0f} "
          f"추세 {last.trend:.0f} 위험선호 {last.risk:.0f} 안전자산 {last.safe:.0f}")
    yr = X.assign(y=X.date.str[:4]).groupby("y").score.mean().round(1)
    print("   연평균: " + " · ".join(f"{y} {v}" for y, v in yr.items()))
    lo = X.nsmallest(3, "score")[["date","score"]].values
    hi = X.nlargest(3, "score")[["date","score"]].values
    print("   최저: " + " · ".join(f"{d} {s:.1f}" for d, s in lo))
    print("   최고: " + " · ".join(f"{d} {s:.1f}" for d, s in hi))
    print()
log(f"저장 완료: {DB.name} · {OUT.name} ({len(R):,}행)")
