# -*- coding: utf-8 -*-
"""스윙매매 기법 실측 — 1단계: 특징 생성 (일봉·주봉·월봉 + 선/눌림/거래량)
   대상: 코스피 생존 944 + 2018년 이후 폐지 77종목 (생존편향 제거)
   저장: data/swing.pkl  (2단계 swing_test.py 에서 사용)
"""
import io, sqlite3, sys, pickle, time
from collections import defaultdict
import numpy as np, pandas as pd
import FinanceDataReader as fdr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
T0 = time.time()
def log(m): print(f"[{time.time()-T0:5.0f}s] {m}", flush=True)

# ── 데이터 ───────────────────────────────────────────────────
c = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True, timeout=300)
SUR = pd.read_sql("""SELECT date,ticker,name,open,high,low,close,volume,frgn FROM daily
    WHERE market='KOSPI' AND close>0 AND open>0 AND date>='20180101' ORDER BY ticker,date""", c); c.close()
c = sqlite3.connect("file:data/delisted.db?mode=ro", uri=True, timeout=300)
DEL = pd.read_sql("""SELECT date,ticker,name,open,high,low,close,volume,frgn FROM daily
    WHERE close>0 AND open>0 AND date>='20180101' ORDER BY ticker,date""", c); c.close()
DEL = DEL[~DEL.ticker.isin(set(SUR.ticker))]
SUR["grp"], DEL["grp"] = "생존", "폐지"
df = pd.concat([SUR, DEL], ignore_index=True)
df = df[df.ticker.str.endswith("0")].sort_values(["ticker", "date"]).reset_index(drop=True)
dates = sorted(df.date.unique()); DI = {d: i for i, d in enumerate(dates)}
log(f"{df.ticker.nunique()}종목 {len(df):,}행 · {dates[0]}~{dates[-1]}")

g = df.groupby("ticker", sort=False)
O, H, L, C, V = df.open, df.high, df.low, df.close, df.volume.astype(float)

# ── 거래량 ───────────────────────────────────────────────────
for w in (5, 20, 60, 120):
    df[f"vma{w}"] = g["volume"].transform(lambda x, w=w: x.rolling(w).mean())
df["vr20"] = V / df.vma20                                   # 당일 / 20일평균
df["vr60"] = V / df.vma60
df["vmax60"] = V / g["volume"].transform(lambda x: x.shift(1).rolling(60).max())   # 60일 신고 거래량 여부
df["vdry"] = df.vma5 / df.vma60                             # 거래량 말라붙음(5일/60일)
df["amt20"] = (V * C).groupby(df.ticker).transform(lambda x: x.rolling(20).mean()) / 1e8
log("거래량")

# ── 캔들 모양 ────────────────────────────────────────────────
rng = (H - L).replace(0, np.nan)
df["body"] = (C - O) / O * 100                              # 몸통 크기(%)
df["bodyr"] = (C - O).abs() / rng                           # 몸통/전체범위
df["uwick"] = (H - np.maximum(O, C)) / rng                  # 윗꼬리 비율
df["lwick"] = (np.minimum(O, C) - L) / rng                  # 아랫꼬리 비율
df["clpos"] = (C - L) / rng                                 # 종가 위치(0=저가,1=고가)
df["chg"] = g.close.transform(lambda x: x / x.shift(1) - 1) * 100
log("캔들")

# ── 이동평균·이격 (종목 자체) ────────────────────────────────
for w in (5, 10, 20, 60, 120, 240):
    df[f"ma{w}"] = g["close"].transform(lambda x, w=w: x.rolling(w).mean())
    df[f"dev{w}"] = C / df[f"ma{w}"] - 1
df["ma5_20"] = df.ma5 > df.ma20
df["ma20_60"] = df.ma20 > df.ma60
df["ma_slope20"] = g["close"].transform(lambda x: x.rolling(20).mean()) / \
                   g["close"].transform(lambda x: x.rolling(20).mean().shift(5)) - 1
log("이평선")

# ── 선(지지/저항) ────────────────────────────────────────────
for w in (20, 60, 120, 240):
    lo = g["low"].transform(lambda x, w=w: x.shift(1).rolling(w).min())
    hi = g["high"].transform(lambda x, w=w: x.shift(1).rolling(w).max())
    df[f"lo{w}"] = lo; df[f"hi{w}"] = hi
    df[f"fromlo{w}"] = C / lo - 1                           # 전저점 대비 위치
    df[f"fromhi{w}"] = C / hi - 1                           # 전고점 대비 위치
    df[f"brk{w}"] = (C > hi) & (g.close.shift(1) <= hi)     # 전고점 돌파(당일)
    df[f"newlo{w}"] = L <= lo                               # 신저가 갱신
df["boxw60"] = df.hi60 / df.lo60 - 1                        # 60일 박스 폭
df["fib"] = (C - df.lo120) / (df.hi120 - df.lo120).replace(0, np.nan)   # 120일 되돌림 위치
log("지지·저항선")

# ── 눌림 (급등 후 조정) ──────────────────────────────────────
df["run20"] = g.close.transform(lambda x: x / x.shift(20) - 1) * 100
df["run60"] = g.close.transform(lambda x: x / x.shift(60) - 1) * 100
df["pull"] = C / g["high"].transform(lambda x: x.rolling(20).max()) - 1   # 최근 20일 고점 대비 눌림
df["pull60"] = C / g["high"].transform(lambda x: x.rolling(60).max()) - 1
df["near20"] = (C / df.ma20 - 1).abs()                      # 20일선 근접도
df["near60"] = (C / df.ma60 - 1).abs()
for n in (3, 5, 10, 20, 60):
    df[f"ret{n}"] = g.close.transform(lambda x, n=n: x / x.shift(n) - 1) * 100
log("눌림")

# ── 변동성 (ATR) ─────────────────────────────────────────────
pc = g.close.shift(1)
tr = pd.concat([H - L, (H - pc).abs(), (L - pc).abs()], axis=1).max(axis=1)
df["atr"] = tr.groupby(df.ticker).transform(lambda x: x.rolling(14).mean())
df["atrp"] = df.atr / C * 100
log("ATR")

# ── 주봉 / 월봉 ──────────────────────────────────────────────
dt = pd.to_datetime(df.date)
df["wk"] = dt.dt.strftime("%G-%V")        # ISO 주
df["mo"] = dt.dt.strftime("%Y-%m")
def bar_feats(key, tag, mas):
    """기간봉 집계 → 해당 기간의 '직전 봉까지' 정보를 일봉 행에 매핑 (미래참조 없음)"""
    agg = df.groupby(["ticker", key]).agg(o=("open", "first"), h=("high", "max"),
                                          l=("low", "min"), c=("close", "last"),
                                          v=("volume", "sum")).reset_index()
    agg = agg.sort_values(["ticker", key])
    gg = agg.groupby("ticker", sort=False)
    for w in mas:
        agg[f"{tag}ma{w}"] = gg["c"].transform(lambda x, w=w: x.rolling(w).mean())
    agg[f"{tag}up"] = agg.c > agg.o                              # 양봉
    agg[f"{tag}chg"] = gg["c"].transform(lambda x: x / x.shift(1) - 1) * 100
    agg[f"{tag}vr"] = agg.v / gg["v"].transform(lambda x: x.shift(1).rolling(12).mean())
    agg[f"{tag}lo"] = gg["l"].transform(lambda x: x.shift(1).rolling(26).min())
    agg[f"{tag}hi"] = gg["h"].transform(lambda x: x.shift(1).rolling(26).max())
    cols = [c for c in agg.columns if c.startswith(tag) and c != key]   # key(wk/mo) 자체는 제외
    prev = agg[["ticker", key] + cols].copy()
    for c in cols: prev[c] = gg[c].shift(1)                      # ★ 직전 봉 값만 사용
    prev[f"{tag}pc"] = gg["c"].shift(1)
    return prev
wk = bar_feats("wk", "w", (5, 12, 26))
mo = bar_feats("mo", "m", (3, 6, 12))
df = df.merge(wk, on=["ticker", "wk"], how="left").merge(mo, on=["ticker", "mo"], how="left")
df["w_above5"] = df.wpc > df.wma5      # 직전 주봉 종가가 5주선 위
df["w_above26"] = df.wpc > df.wma26
df["m_above6"] = df.mpc > df.mma6
df["m_above12"] = df.mpc > df.mma12
df["w_fromlo"] = df.wpc / df.wlo - 1
log("주봉·월봉")

# ── 시장 ─────────────────────────────────────────────────────
ki = fdr.DataReader("KS11", "2016-06-01"); ki = ki[ki.Close > 0]; ki.index = ki.index.strftime("%Y%m%d")
kc = ki["Close"].reindex(dates).ffill()
for w in (5, 20, 60, 120):
    df[f"K{w}"] = df.date.map(kc > kc.rolling(w).mean()).fillna(False).values
df["Kret20"] = df.date.map(kc / kc.shift(20) - 1).astype(float) * 100

# ── 공매도·증자 ──────────────────────────────────────────────
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
ds = pd.to_datetime(df.date); dil = np.zeros(len(df), bool)
for t, idx in df.groupby("ticker").indices.items():
    Ls = pd.to_datetime(DIL.get(t, []))
    if len(Ls) == 0: continue
    for i, x in zip(idx, ds.values[idx]):
        dil[i] = bool(((Ls.values >= x - np.timedelta64(90, "D")) & (Ls.values <= x)).any())
df["dil"] = dil
v5s = g["volume"].transform(lambda x: x.rolling(5).sum())
df["fw5"] = g["frgn"].transform(lambda x: x.fillna(0).rolling(5).sum()) / v5s.replace(0, np.nan) * 100
df["fw20"] = g["frgn"].transform(lambda x: x.fillna(0).rolling(20).sum()) / \
             g["volume"].transform(lambda x: x.rolling(20).sum()).replace(0, np.nan) * 100
log("시장·수급")

# ── 비용 · 불연속 ────────────────────────────────────────────
df["cost"] = 0.18 + np.select([df.amt20 >= 100, df.amt20 >= 50, df.amt20 >= 20, df.amt20 >= 10],
                              [.20, .30, .50, .70], default=1.00)
jj = (C / pc).where(pc > 0)
badday = ((jj > 1.32) | (jj < 0.68)).fillna(False)
bad = np.zeros(len(df), bool); pos = df.date.map(DI).values
for t, sub in df[badday].groupby("ticker"):
    idx = df.index[df.ticker == t].values
    bp = np.sort([DI[x] for x in sub.date if x in DI]); p = pos[idx]
    q = np.searchsorted(bp, p, side="right")
    bad[idx[(q < len(bp)) & (bp[np.minimum(q, len(bp) - 1)] - p <= 60)]] = True
df["bad"] = bad
df["y"] = df.date.str[:4].astype(int)
df["pos"] = pos
log(f"불연속 제외 {int(bad.sum()):,}행")

keep = [c for c in df.columns if c not in ("wk", "mo")]
df[keep].to_pickle("data/swing.pkl")
log(f"저장 완료 data/swing.pkl · {len(df):,}행 × {len(keep)}열")
