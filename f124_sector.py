# -*- coding: utf-8 -*-
"""1·2·4번 필터 + 업종 조건 실측
   코스피(1·2번): sector.csv 업종 · 코스닥(4번): KRX-DESC Industry(표준산업분류)
   업종 데이터 없으면 통과(3번과 동일 정책)
"""
import io, sqlite3, sys, csv, time
from collections import defaultdict
import numpy as np, pandas as pd
import FinanceDataReader as fdr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
T0 = time.time()
def log(m): print(f"[{time.time()-T0:4.0f}s] {m}", flush=True)
CASH = 3_000_000

def build(market):
    """market: 'KOSPI' or 'KOSDAQ' — 생존 + 폐지 결합"""
    if market == "KOSPI":
        c = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True, timeout=300)
        A = pd.read_sql("""SELECT date,ticker,name,open,high,low,close,volume,frgn FROM daily
            WHERE market='KOSPI' AND close>0 AND open>0 AND date>='20180101' ORDER BY ticker,date""", c); c.close()
        c = sqlite3.connect("file:data/delisted.db?mode=ro", uri=True, timeout=300)
        B = pd.read_sql("""SELECT date,ticker,name,open,high,low,close,volume,frgn FROM daily
            WHERE close>0 AND open>0 AND date>='20180101' ORDER BY ticker,date""", c); c.close()
        AMT1, AMT2 = 50.0, 3.0
    else:
        c = sqlite3.connect("file:data/kosdaq.db?mode=ro", uri=True, timeout=300)
        A = pd.read_sql("""SELECT date,ticker,name,open,high,low,close,volume,frgn FROM daily
            WHERE close>0 AND open>0 ORDER BY ticker,date""", c); c.close()
        DT = set(pd.read_csv("data/kosdaq_delisted.csv", dtype=str).Symbol)
        c = sqlite3.connect("file:data/delisted_kd.db?mode=ro", uri=True, timeout=300)
        B = pd.read_sql("""SELECT date,ticker,name,open,high,low,close,volume,frgn FROM daily
            WHERE close>0 AND open>0 AND date>='20210101' ORDER BY ticker,date""", c); c.close()
        B = B[B.ticker.isin(DT)]
        AMT1, AMT2 = 20.0, 2.0
    B = B[~B.ticker.isin(set(A.ticker))]
    A["grp"], B["grp"] = "생존", "폐지"
    df = pd.concat([A, B], ignore_index=True)
    df = df[df.ticker.str.endswith("0")].sort_values(["ticker", "date"]).reset_index(drop=True)
    return df, AMT1, AMT2

def prep(df, market, AMT1, AMT2):
    dates = sorted(df.date.unique()); DI = {d: i for i, d in enumerate(dates)}
    k = sqlite3.connect("file:data/kis/market.db?mode=ro", uri=True, timeout=300)
    ss = pd.read_sql("SELECT date,ticker,short_ratio FROM short_sale WHERE short_ratio IS NOT NULL ORDER BY ticker,date", k); k.close()
    ss = ss[ss.ticker.isin(set(df.ticker))]
    gs = ss.groupby("ticker").short_ratio
    ss["srd"] = gs.transform(lambda x: x.rolling(5).mean()) < gs.transform(lambda x: x.rolling(20).mean())
    df = df.merge(ss[["date", "ticker", "srd"]], on=["date", "ticker"], how="left")
    d = sqlite3.connect("file:data/dart/disclosures.db?mode=ro", uri=True, timeout=300)
    dz = pd.read_sql("""SELECT stock_code t, rcept_dt FROM disclosure WHERE
       replace(report_nm,' ','') LIKE '%유상증자결정%' OR replace(report_nm,' ','') LIKE '%전환사채권발행결정%'
       OR replace(report_nm,' ','') LIKE '%신주인수권부사채권발행결정%'""", d); d.close()
    DIL = defaultdict(list)
    for r in dz.itertuples(): DIL[r.t].append(r.rcept_dt)
    ki = fdr.DataReader("KS11", "2016-06-01"); ki = ki[ki.Close > 0]; ki.index = ki.index.strftime("%Y%m%d")
    kc = ki["Close"].reindex(dates).ffill()
    for w in (5, 20, 60): df[f"K{w}"] = df.date.map(kc > kc.rolling(w).mean()).fillna(False).values
    g = df.groupby("ticker", sort=False); V, C = df.volume.astype(float), df.close
    df["vm3"] = g["volume"].transform(lambda x: x.rolling(3).mean())
    df["a40"] = g["volume"].transform(lambda x: x.shift(3).rolling(40).mean())
    df["a240"] = g["volume"].transform(lambda x: x.shift(43).rolling(240).mean())
    df["r16"] = df.a40 / df.a240 * 100; df["rw1"] = df.vm3 / df.a40 * 100
    df["su1"] = V / g["volume"].transform(lambda x: x.shift(1).rolling(20).mean())
    df["amt"] = (V * C).groupby(df.ticker).transform(lambda x: x.rolling(40).mean()).shift(3) / 1e8
    df["amt20"] = (V * C).groupby(df.ticker).transform(lambda x: x.rolling(20).mean()) / 1e8
    v5s = g["volume"].transform(lambda x: x.rolling(5).sum())
    df["fw5"] = g["frgn"].transform(lambda x: x.fillna(0).rolling(5).sum()) / v5s.replace(0, np.nan) * 100
    df["fw60"] = g["frgn"].transform(lambda x: x.fillna(0).rolling(60).sum()) / \
                 g["volume"].transform(lambda x: x.rolling(60).sum()).replace(0, np.nan) * 100
    for n in (3, 10, 20, 60): df[f"ret{n}"] = g.close.transform(lambda x, n=n: x / x.shift(n) - 1) * 100
    op1 = g.open.shift(-1); df["buy"] = op1; df["gap"] = (op1 / C - 1) * 100
    df["y"] = df.date.str[:4].astype(int)
    ds = pd.to_datetime(df.date); dil = np.zeros(len(df), bool)
    for t, idx in df.groupby("ticker").indices.items():
        L = pd.to_datetime(DIL.get(t, []))
        if len(L) == 0: continue
        for i, x in zip(idx, ds.values[idx]):
            dil[i] = bool(((L.values >= x - np.timedelta64(90, "D")) & (L.values <= x)).any())
    df["dil"] = dil
    slip = [.20, .30, .50, .70] if market == "KOSPI" else [.30, .50, .70, 1.00]
    dflt = 1.00 if market == "KOSPI" else 1.50
    df["cost"] = 0.18 + np.select([df.amt20 >= 100, df.amt20 >= 50, df.amt20 >= 20, df.amt20 >= 10], slip, default=dflt)
    pc = g.close.shift(1); jj = (C / pc).where(pc > 0)
    badday = ((jj > 1.32) | (jj < 0.68)).fillna(False)
    bad = np.zeros(len(df), bool); pos = df.date.map(DI).values
    for t, sub in df[badday].groupby("ticker"):
        idx = df.index[df.ticker == t].values
        bp = np.sort([DI[x] for x in sub.date if x in DI]); p = pos[idx]
        q = np.searchsorted(bp, p, side="right")
        bad[idx[(q < len(bp)) & (bp[np.minimum(q, len(bp) - 1)] - p <= 42)]] = True
    lastpos = g.date.transform("max").map(DI); lastclose = g.close.transform("last"); mypos = df.date.map(DI)
    for h in (10, 20):
        sell = g.close.shift(-h)
        df[f"f{h}"] = (sell.where(~(mypos + h > lastpos), lastclose) / df.buy - 1) * 100
    hi10 = g.high.shift(-1).rolling(10, min_periods=1).max().shift(-9)
    df["f10t"] = np.where(hi10 >= df.buy * 1.20, 20.0, df.f10)
    # ── 업종 ──
    if market == "KOSPI":
        UP = {r["ticker"]: r["gname"] for r in csv.DictReader(open("data/sector.csv", encoding="utf-8"))
              if r["kind"] == "upjong"}
    else:
        dd = fdr.StockListing("KRX-DESC")
        UP = {r.Code: r.Industry for r in dd.itertuples()
              if isinstance(r.Code, str) and isinstance(r.Industry, str) and r.Industry}
    df["up"] = df.ticker.map(UP)
    src = df[df.up.notna() & df.ret60.notna()]
    sa = src.groupby(["date", "up"]).agg(sret60=("ret60", "mean"), cnt=("ticker", "size")).reset_index()
    sa = sa[sa.cnt >= 5]
    df = df.merge(sa[["date", "up", "sret60"]], on=["date", "up"], how="left")
    return df[~bad & df.buy.notna()].reset_index(drop=True)

def ev(D, m, col):
    x = D[m.fillna(False)]
    r = (x[col] - x.cost).values; y = x.y.values
    ok = np.isfinite(r); r, y = r[ok], y[ok]
    if len(r) < 10: return None
    rs = np.sort(r); yy = pd.Series(r).groupby(y).agg(["mean", "size"]); yy = yy[yy["size"] >= 3]
    cut = 2022 if len(set(y)) > 6 else 2023
    return dict(n=len(r), ret=r.mean(), med=np.median(r), win=(r > 0).mean()*100,
                pf=(r[r>0].sum()/abs(r[r<=0].sum())) if (r<=0).any() else 99.,
                is_=r[y <= cut].mean(), os_=r[y > cut].mean(),
                t5=rs[:-5].mean() if len(rs) > 5 else np.nan, worst=r.min(),
                pos=int((yy["mean"] > 0).sum()), ny=len(yy), tot=r.sum()/100*CASH)
HDR = ("| 조건 | 신호 | 절대수익 | 중앙값 | 승률 | PF | 상위5제외 | 학습 | 검증 | +연도 | 최악 | 300만씩 |\n"
       "|---|---|---|---|---|---|---|---|---|---|---|---|")
def row(D, lab, m, col):
    s = ev(D, m, col)
    if not s: return print(f"| {lab} | {int(m.fillna(False).sum())} | 10건 미만 |" + " - |" * 10)
    print(f"| {lab} | {s['n']} | **{s['ret']:+.2f}%** | {s['med']:+.2f}% | {s['win']:.0f}% | {s['pf']:.2f} | "
          f"{s['t5']:+.2f}% | {s['is_']:+.2f}% | **{s['os_']:+.2f}%** | {s['pos']}/{s['ny']} | {s['worst']:+.0f}% | "
          f"**{s['tot']/10000:+,.0f}만** |")

# ═══ 코스피 1·2번 ═══════════════════════════════════════════
df, A1, A2 = build("KOSPI"); D = prep(df, "KOSPI", A1, A2)
log(f"코스피 평가 {len(D):,}행 · 업종수익 {D.sret60.notna().sum():,}행")
F1 = ((D.r16 < 50) & (D.rw1 >= 200) & (D.fw5 >= 3) & (D.amt >= A1) & D.ret10.between(0, 20)
      & D.K5 & D.K20 & (D.srd == True) & (D.gap < 5))
F2 = ((D.r16 < 30) & (D.rw1 >= 200) & (D.fw5 >= 2) & (D.amt >= A2) & (D.ret3 <= -5)
      & (D.ret10 <= 0) & (~D.K20) & (D.srd == True) & (~D.dil))
NA = D.sret60.isna()
for lab, F, col in (("1번 상승초입 (10일·익절+20%)", F1, "f10t"), ("2번 조정매집 (10일)", F2, "f10")):
    print(f"\n## {lab} + 업종 조건 (업종 데이터 없으면 통과)\n"); print(HDR)
    row(D, "현행 (업종 조건 없음)", F, col)
    for th in (-20, -10, -5, 0):
        row(D, f"+ 업종 60일 {th}% 이하", F & (NA | (D.sret60 <= th)), col)
    print("(반대 방향)")
    for th in (0, 10, 20):
        row(D, f"+ 업종 60일 {th}% 이상 (업종 강세)", F & (NA | (D.sret60 >= th)), col)

# ═══ 코스닥 4번 ═════════════════════════════════════════════
df, A1, A2 = build("KOSDAQ"); K = prep(df, "KOSDAQ", A1, A2)
log(f"코스닥 평가 {len(K):,}행 · 업종수익 {K.sret60.notna().sum():,}행 · 업종수 {K.up.nunique()}")
F4 = ((K.ret20 <= -20) & (K.su1 >= 2) & (K.fw60 >= 1) & (K.amt20 >= A2)
      & (~K.K60) & (K.srd == True) & (~K.dil))
NA4 = K.sret60.isna()
print(f"\n## 4번 낙폭과대 (코스닥·20일) + 업종 조건\n"); print(HDR)
row(K, "현행 (업종 조건 없음)", F4, "f20")
for th in (-25, -20, -15, -10, -5, 0):
    row(K, f"+ 업종 60일 {th}% 이하", F4 & (NA4 | (K.sret60 <= th)), "f20")
print("(반대 방향)")
row(K, "+ 업종 60일 0% 이상 (업종 강세)", F4 & (NA4 | (K.sret60 >= 0)), "f20")
log("완료")
