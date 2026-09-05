# -*- coding: utf-8 -*-
"""공포탐욕지수 증분 갱신 — 매일 수집 워크플로에서 돌린다.

`collect_feargreed.py` 는 2005년부터 전 구간을 다시 만드는 도구라 kospi.db(1GB, 저장소에 없음)가 필요하다.
이 스크립트는 **이미 커밋된 data/feargreed.csv 의 원시값(raw_*) 이력을 그대로 이어받아 새 날짜만 계산**한다.
그래서 CI 에서도 돌고, 과거 구간(2005~2017)을 잘못 덮어쓸 일이 없다.

새 날짜의 원시값 출처
  지수·환율   FinanceDataReader (KS11 · KQ11 · USD/KRW)
  변동성      data/vkospi.csv  ← collect_vkospi.py 를 **먼저** 돌릴 것
  코스피 종목  data/YYYY-MM.csv (저장소에 있음) · kospi.db 가 있으면 그걸 먼저 쓴다
  코스닥 종목  data/kosdaq.db (워크플로 캐시로 복원) · 없으면 코스닥 갱신만 건너뛴다

정규화는 이력+신규를 합친 뒤 다시 계산한다(변동성만 확장창, 나머지는 3년 롤링).
사용: python update_feargreed.py
"""
import glob, os, sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

BASE = Path(__file__).parent
CSV = BASE / "data" / "feargreed.csv"
DB = BASE / "data" / "feargreed.db"
sys.stdout.reconfigure(encoding="utf-8")
t0 = time.time()
def log(m): print(f"[{(time.time()-t0)/60:5.1f}분] {m}", flush=True)

if not CSV.exists():
    sys.exit("data/feargreed.csv 가 없다 — collect_feargreed.py 로 먼저 전 구간을 만들 것")
H = pd.read_csv(CSV, dtype={"date": str})
RAW = [c for c in H.columns if c.startswith("raw_")]
last = H.groupby("market").date.max().to_dict()
log(f"이력 {len(H):,}행 · 마지막 " + " · ".join(f"{k} {v}" for k, v in last.items()))

# ── 지수·환율 ───────────────────────────────────────────────────
def idx(code):
    d = fdr.DataReader(code, "2003-01-01"); d = d[d.Close > 0].copy()
    d.index = pd.to_datetime(d.index); return d.Close.rename(code)
# 원/달러는 휴장일에도 값이 있어 그대로 ffill 하면 휴장일이 거래일이 된다 — 코스피 거래일로 자른다
_ks = idx("KS11")
IX = pd.concat([_ks, idx("KQ11"), idx("USD/KRW")], axis=1).sort_index()
IX = IX.loc[_ks.index].ffill().dropna(subset=["KS11", "KQ11"]); IX["date"] = IX.index.strftime("%Y%m%d")
log(f"지수 {len(IX)}거래일 · 최신 {IX.date.iloc[-1]}")

VK = {}
vf = BASE / "data" / "vkospi.csv"
if vf.exists():
    V = pd.read_csv(vf, dtype={"date": str}); VK = dict(zip(V.date, V.close))
    log(f"VKOSPI {len(V):,}일 · 최신 {V.date.iloc[-1]}")
else:
    log("⚠ data/vkospi.csv 없음 — 변동성은 실현변동성으로 대체된다")

# ── 종목 단위(최근분만) ─────────────────────────────────────────
def recent_stocks(market, need_from):
    """52주 고저·상승하락 거래량을 내려면 넉넉히 400거래일 정도 과거가 필요하다."""
    kdb, qdb = BASE/"data"/"kospi.db", BASE/"data"/"kosdaq.db"
    if os.environ.get("FG_CSV_ONLY"): kdb = BASE/"data"/"_none_"   # CI 경로 시험용
    if market == "KOSPI":
        if kdb.exists():
            c = sqlite3.connect(f"file:{kdb}?mode=ro", uri=True, timeout=600)
            S = pd.read_sql("SELECT date,ticker,close,volume FROM daily WHERE date>=? AND close>0 "
                            "AND (market='KOSPI' OR market IS NULL)", c, params=(need_from,)); c.close()
            return S
        fs = sorted(glob.glob(str(BASE/"data"/"20??-??.csv")))
        fs = [f for f in fs if Path(f).stem.replace("-", "") + "01" >= need_from[:6] + "01"]
        if not fs: return None
        S = pd.concat([pd.read_csv(f, dtype={"date": str, "ticker": str},
                                   usecols=["date","ticker","close","volume","market"]) for f in fs], ignore_index=True)
        S = S[(S.market.isna()) | (S.market == "KOSPI")]
        return S[S.close > 0][["date","ticker","close","volume"]]
    if not qdb.exists(): return None
    c = sqlite3.connect(f"file:{qdb}?mode=ro", uri=True, timeout=600)
    S = pd.read_sql("SELECT date,ticker,close,volume FROM daily WHERE date>=? AND close>0", c,
                    params=(need_from,)); c.close()
    return S

def breadth(S):
    S = S.drop_duplicates(["ticker","date"]).sort_values(["ticker","date"])
    g = S.groupby("ticker", sort=False)
    hi = g.close.transform(lambda s: s.rolling(250, min_periods=120).max())
    lo = g.close.transform(lambda s: s.rolling(250, min_periods=120).min())
    S = S.assign(nh=(S.close >= hi*0.999).astype(float), nl=(S.close <= lo*1.001).astype(float),
                 valid=hi.notna().astype(float), chg=g.close.diff())
    S["upv"] = np.where(S.chg > 0, S.volume, 0.0); S["dnv"] = np.where(S.chg < 0, S.volume, 0.0)
    D = S.groupby("date").agg(nh=("nh","sum"), nl=("nl","sum"), valid=("valid","sum"),
                              upv=("upv","sum"), dnv=("dnv","sum"))
    D["strength"] = (D.nh - D.nl) / D.valid.replace(0, np.nan) * 100
    b = (D.upv - D.dnv) / (D.upv + D.dnv).replace(0, np.nan) * 100
    D["bread20"] = b.rolling(20, min_periods=15).mean()
    return D

def new_rows(market):
    lastd = last.get(market)
    new = IX[IX.date > lastd]
    if new.empty: log(f"  {market} 새 거래일 없음 ({lastd} 까지 최신)"); return None
    need_from = (pd.to_datetime(lastd) - pd.Timedelta(days=650)).strftime("%Y%m%d")
    S = recent_stocks(market, need_from)
    if S is None or S.empty:
        log(f"  ⚠ {market} 종목 데이터를 못 읽었다 — 이 시장은 건너뛴다"); return None
    B = breadth(S)
    px = IX["KS11"] if market == "KOSPI" else IX["KQ11"]
    F = pd.DataFrame({"date": IX.date})
    r1 = px.pct_change()
    F["raw_vol20"] = (r1.rolling(20).std()*np.sqrt(252)*100).values
    F["raw_mom"] = (px/px.rolling(125).mean()*100 - 100).values
    F["raw_trend"] = (px.pct_change(20)*100).values
    F["raw_risk"] = (IX.KQ11.pct_change(20)*100 - IX.KS11.pct_change(20)*100).values
    F["raw_safe"] = (px.pct_change(20)*100 - IX["USD/KRW"].pct_change(20)*100).values
    bb = B.reindex(IX.date.values)
    F["raw_strength"] = bb.strength.values; F["raw_bread"] = bb.bread20.values
    F["raw_nh"] = bb.nh.values; F["raw_nl"] = bb.nl.values
    F["raw_vk"] = F.date.map(VK)
    F["raw_volsrc"] = F.raw_vk.where(F.raw_vk.notna(), F.raw_vol20)
    F = F[F.date > lastd].dropna(subset=["raw_strength", "raw_volsrc"])
    if F.empty: log(f"  {market} 새 날짜의 종목 집계가 비었다 — 건너뛴다"); return None
    F["market"] = market
    log(f"  {market} 새 {len(F)}일 추가 ({F.date.iloc[0]}~{F.date.iloc[-1]})")
    return F

NEW = [x for x in (new_rows(m) for m in ("KOSPI", "KOSDAQ")) if x is not None]
if not NEW:
    log("갱신할 것이 없다"); sys.exit(0)
A = pd.concat([H[["date","market"]+RAW]] + NEW, ignore_index=True)
A = A.drop_duplicates(["market","date"], keep="last").sort_values(["market","date"])

# ── 정규화 다시 ────────────────────────────────────────────────
def pctile(s, win=750, minp=250):
    return s.rolling(win, min_periods=minp).apply(lambda x: (x[:-1] < x[-1]).mean()*100 if len(x) > 1 else np.nan, raw=True)
def pct_exp(s, minp=500):
    return s.rolling(len(s), min_periods=minp).apply(lambda x: (x[:-1] < x[-1]).mean()*100 if len(x) > 1 else np.nan, raw=True)
W = {"volatility":0.30, "momentum":0.25, "strength":0.15, "trend":0.15, "risk":0.10, "safe":0.05}
out = []
for m, F in A.groupby("market"):
    F = F.reset_index(drop=True)
    N = pd.DataFrame({"date": F.date, "market": m})
    N["volatility"] = 100 - pct_exp(F.raw_volsrc)
    N["volatility_rv"] = 100 - pctile(F.raw_volsrc)
    N["momentum"] = pctile(F.raw_mom); N["strength"] = pctile(F.raw_strength)
    N["trend"] = pctile(F.raw_trend); N["risk"] = pctile(F.raw_risk)
    N["safe"] = pctile(F.raw_safe); N["breadth"] = pctile(F.raw_bread)
    num = sum(N[k].fillna(0)*w for k, w in W.items()); den = sum(N[k].notna()*w for k, w in W.items())
    N["score"] = (num/den.replace(0, np.nan)).round(1)
    num2 = sum(N[k].fillna(0)*w for k, w in W.items() if k != "volatility") + N.volatility_rv.fillna(0)*W["volatility"]
    den2 = sum(N[k].notna()*w for k, w in W.items() if k != "volatility") + N.volatility_rv.notna()*W["volatility"]
    N["score_rv"] = (num2/den2.replace(0, np.nan)).round(1)
    for c in RAW: N[c] = F[c].values
    out.append(N.dropna(subset=["score"]))
N2 = pd.concat(out, ignore_index=True)
cols = ["date","market","score","score_rv","volatility","volatility_rv","momentum","strength","trend","risk","safe","breadth"] + RAW
# ⚠ 이력 행은 '전 구간으로 계산된' 값이라 그대로 둔다. 재계산본으로 덮으면 정규화 창이 짧아져
#   앞쪽이 매번 250일씩 잘려 나간다(실제로 12,022행 → 11,513행이 됐다).
old_keys = set(zip(H.market, H.date))
add = N2[[ (m, d) not in old_keys for m, d in zip(N2.market, N2.date)]]
R = pd.concat([H[cols], add[cols]], ignore_index=True).drop_duplicates(["market","date"], keep="first")
R = R.sort_values(["market","date"])
log(f"이력 {len(H):,}행 유지 + 새로 {len(add):,}행")
for c in R.columns:
    if c not in ("date","market"): R[c] = R[c].astype(float).round(3)
R.to_csv(CSV, index=False, encoding="utf-8-sig")
con = sqlite3.connect(DB)
con.execute("DROP TABLE IF EXISTS feargreed")
con.execute("CREATE TABLE feargreed(" + ",".join(f"{c} TEXT" if c in ("date","market") else f"{c} REAL" for c in cols)
            + ", PRIMARY KEY(date,market))")
con.executemany(f"INSERT OR REPLACE INTO feargreed VALUES({','.join('?'*len(cols))})",
                R.itertuples(index=False, name=None))
con.commit(); con.close()
band = lambda v: "극단적 공포" if v < 25 else "공포" if v < 45 else "중립" if v < 55 else "탐욕" if v < 75 else "극단적 탐욕"
for m in R.market.unique():
    x = R[R.market == m].iloc[-1]
    print(f"  {m} {x.date}: {x.score:.1f} ({band(x.score)}) · VKOSPI {x.raw_vk if x.raw_vk==x.raw_vk else float('nan'):.2f}")
log(f"저장 완료 {len(R):,}행 ({R.date.min()}~{R.date.max()})")
