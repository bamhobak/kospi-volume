# -*- coding: utf-8 -*-
"""일일 파이프라인용 코스닥 수집 (최근 60거래일) → data/kosdaq.db
   코스닥 필터가 쓰는 값은 ret20 · vs1(당일/직전20일) · fw60(외국인 60일) · amt20 뿐이라
   60거래일 창이면 충분하다. 시세는 네이버 trend API 한 번 호출로 60일치를 받는다.
   과거 전체 이력은 로컬 백테스트용으로만 두고 리포지토리에는 커밋하지 않는다.
사용: python collect_kosdaq_daily.py [--days 60]
"""
import sqlite3, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import pandas as pd, requests
import FinanceDataReader as fdr
import collect

log = collect.log
BASE = Path(__file__).parent
DB = BASE / "data" / "kosdaq.db"
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
DAYS = int(arg("--days", "60"))          # 네이버 trend API 최대 60
HDR = {"User-Agent": "Mozilla/5.0"}
WORKERS = 8
num = collect.num

con = sqlite3.connect(DB, timeout=900)
con.execute("""CREATE TABLE IF NOT EXISTS daily(
    date TEXT, ticker TEXT, name TEXT, close INTEGER, change INTEGER, volume INTEGER,
    open INTEGER, high INTEGER, low INTEGER, market TEXT,
    indiv INTEGER, organ INTEGER, frgn INTEGER, foreign_ratio REAL, marcap REAL,
    PRIMARY KEY(date, ticker))""")
con.execute("CREATE INDEX IF NOT EXISTS ix_kd_ticker ON daily(ticker, date)")
con.commit()

try:
    with ThreadPoolExecutor(1) as ex:
        listing = ex.submit(lambda: fdr.StockListing("KOSDAQ")).result(timeout=90)
    CODES = [(r.Code, r.Name) for r in listing.itertuples(index=False)
             if isinstance(r.Code, str) and len(r.Code) == 6]
except Exception as e:
    log.warning(f"코스닥 목록(FDR) 실패 → DB 목록 사용: {str(e)[:60]}")
    CODES = con.execute("SELECT ticker, max(name) FROM daily GROUP BY ticker").fetchall()
log.info(f"코스닥 {len(CODES)}종목 · 최근 {DAYS}거래일 수집")

def one(code, name):
    url = f"https://m.stock.naver.com/api/stock/{code}/trend?pageSize={DAYS}&page=1"
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HDR, timeout=15); r.raise_for_status()
            out = []
            for it in r.json():
                out.append((it["bizdate"], code, name, num(it["closePrice"]),
                            num(it["compareToPreviousClosePrice"]), num(it["accumulatedTradingVolume"]),
                            num(it["individualPureBuyQuant"]), num(it["organPureBuyQuant"]),
                            num(it["foreignerPureBuyQuant"]), num(it["foreignerHoldRatio"]), "KOSDAQ"))
            return out
        except Exception:
            time.sleep(1.5)
    return []

UPS = ("INSERT INTO daily (date,ticker,name,close,change,volume,indiv,organ,frgn,foreign_ratio,market) "
       "VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(date,ticker) DO UPDATE SET "
       "name=excluded.name, close=excluded.close, change=excluded.change, volume=excluded.volume, "
       "indiv=excluded.indiv, organ=excluded.organ, frgn=excluded.frgn, "
       "foreign_ratio=excluded.foreign_ratio, market=excluded.market")
n = tot = 0; t0 = time.time()
with ThreadPoolExecutor(WORKERS) as ex:
    for f in as_completed([ex.submit(one, c, nm) for c, nm in CODES]):
        rows = f.result()
        if rows: con.executemany(UPS, rows); tot += len(rows)
        n += 1
        if n % 300 == 0: con.commit(); log.info(f"진행 {n}/{len(CODES)} ({tot:,}행)")
con.commit()
d0, d1 = con.execute("SELECT min(date), max(date) FROM daily").fetchone()
log.info(f"코스닥 완료: {tot:,}행 반영 ({time.time()-t0:.0f}s) · DB "
         f"{con.execute('SELECT count(*) FROM daily').fetchone()[0]:,}행 {d0}~{d1}")
con.close()
