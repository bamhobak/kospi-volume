"""과거 OHLC·시가총액 백필 (1회성)
- OHLC: FinanceDataReader 로 종목별 일별 시가/고가/저가 채움
- 거래대금(amount): 실제값이 없는 과거는 종가×거래량으로 근사
- 시가총액(marcap): 종가 × 현재 상장주식수(근사) — 상장주식수 변동은 무시
사용: python backfill_ohlc.py [시작일 YYYY-MM-DD]
"""
import sqlite3, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import FinanceDataReader as fdr
import collect

FROM = sys.argv[1] if len(sys.argv) > 1 else "2023-01-01"
log = collect.log
con = sqlite3.connect(collect.DB, timeout=120)
collect.init_db(con)

listing = collect.get_listing()
shares = {r.Code: int(r.Stocks) for r in listing.itertuples(index=False)
          if getattr(r, "Stocks", None) == getattr(r, "Stocks", None) and getattr(r, "Stocks", None)}
codes = [r.Code for r in listing.itertuples(index=False)]
log.info(f"OHLC 백필 {len(codes)}종목 · {FROM}~")

def one(code):
    try:
        d = fdr.DataReader(code, FROM)
        if d is None or len(d) == 0: return []
        out = []
        sh = shares.get(code)
        for dt_, r in d.iterrows():
            try:
                c = int(r["Close"]); v = int(r["Volume"])
                out.append((int(r["Open"]), int(r["High"]), int(r["Low"]), c * v,
                            (c * sh) if sh else None, sh, dt_.strftime("%Y%m%d"), code))
            except Exception: pass
        return out
    except Exception as e:
        log.warning(f"{code}: {e}"); return []

n = total = 0
with ThreadPoolExecutor(8) as ex:
    futs = [ex.submit(one, c) for c in codes]
    for f in as_completed(futs):
        rows = f.result()
        if rows:
            con.executemany("""UPDATE daily SET open=COALESCE(open,?), high=COALESCE(high,?), low=COALESCE(low,?),
                               amount=COALESCE(amount,?), marcap=COALESCE(marcap,?), shares=COALESCE(shares,?)
                               WHERE date=? AND ticker=?""", rows)
            total += len(rows)
        n += 1
        if n % 100 == 0: con.commit(); log.info(f"진행 {n}/{len(codes)} ({total}행)")
con.commit()
r = con.execute("SELECT count(*), sum(open IS NOT NULL), sum(marcap IS NOT NULL) FROM daily WHERE date>=?", (FROM.replace("-", ""),)).fetchone()
print(f"완료: {FROM} 이후 {r[0]:,}행 중 OHLC {r[1]:,}행 · 시총 {r[2]:,}행")
con.close()
