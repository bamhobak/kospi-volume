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
BACKFILL = int(arg("--backfill", "0"))   # >0 이면 시세가 N거래일 미만일 때 FDR 로 종가 백필.
                                         # 네이버 trend API 는 60일이 최대라 3M/6M/1Y 수익률을 못 만든다.
PRUNE = int(arg("--prune", "0"))         # >0 이면 최근 N거래일만 남김 (CI 캐시 크기 제한용).
                                         # 로컬 백테스트 DB는 기본값 0 이라 절대 지우지 않는다.
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
    CAP = {r.Code: r.Marcap for r in listing.itertuples(index=False)
           if isinstance(r.Code, str) and getattr(r, "Marcap", None) == getattr(r, "Marcap", None)}
except Exception as e:
    log.warning(f"코스닥 목록(FDR) 실패 → DB 목록 사용: {str(e)[:60]}")
    CODES = con.execute("SELECT ticker, max(name) FROM daily GROUP BY ticker").fetchall(); CAP = {}
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
# ── 기간 수익률용 종가 백필 (FDR) ──────────────────────────
# trend API 는 60일이 최대 → 3개월(61)·6개월(121)·1년(241) 수익률을 만들 수 없다.
# 투자자 데이터는 그대로 두고 종가·거래량만 채운다.
if BACKFILL > 0:
    have = con.execute("SELECT count(DISTINCT date) FROM daily").fetchone()[0]
    if have < BACKFILL:
        import datetime as _dt
        frm = (_dt.date.today() - _dt.timedelta(days=int(BACKFILL * 1.6))).strftime("%Y-%m-%d")
        log.info(f"시세 {have}일 보유 < {BACKFILL}일 → FDR 백필 {frm}~")
        UPB = ("INSERT INTO daily (date,ticker,name,close,change,volume,open,high,low,market) "
               "VALUES (?,?,?,?,?,?,?,?,?,'KOSDAQ') ON CONFLICT(date,ticker) DO UPDATE SET "
               "close=excluded.close, change=excluded.change, volume=excluded.volume, "
               "open=excluded.open, high=excluded.high, low=excluded.low, market='KOSDAQ'")
        def bf(code, name):
            try:
                d = fdr.DataReader(code, frm)
                if d is None or len(d) == 0: return []
                out, prev = [], None
                for dt_, r in d.iterrows():
                    if not r["Close"] or r["Close"] != r["Close"]: continue
                    c = int(r["Close"]); ch = None if prev is None else c - prev; prev = c
                    out.append((dt_.strftime("%Y%m%d"), code, name, c, ch, int(r["Volume"]),
                                int(r["Open"]), int(r["High"]), int(r["Low"])))
                return out
            except Exception: return []
        n2 = t2 = 0; tb = time.time()
        with ThreadPoolExecutor(WORKERS) as ex:
            for f in as_completed([ex.submit(bf, c, nm) for c, nm in CODES]):
                rws = f.result()
                if rws: con.executemany(UPB, rws); t2 += len(rws)
                n2 += 1
                if n2 % 400 == 0: con.commit(); log.info(f"백필 {n2}/{len(CODES)} ({t2:,}행)")
        con.commit()
        log.info(f"백필 완료: {t2:,}행 ({time.time()-tb:.0f}s) · 거래일 "
                 f"{con.execute('SELECT count(DISTINCT date) FROM daily').fetchone()[0]}일")

# 시가총액 스냅샷 (최신 거래일 행에 반영) — 전체 종목 목록 정렬용
if CAP:
    last = con.execute("SELECT max(date) FROM daily").fetchone()[0]
    rows = [(int(v), last, t) for t, v in CAP.items() if v and v == v]
    con.executemany("UPDATE daily SET marcap=? WHERE date=? AND ticker=?", rows)
    con.commit(); log.info(f"시가총액 반영 {len(rows):,}종목 ({last})")
con.commit()
if PRUNE > 0:
    keep = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily ORDER BY date DESC LIMIT ?", (PRUNE,))]
    if keep:
        n0 = con.execute("SELECT count(*) FROM daily").fetchone()[0]
        con.execute("DELETE FROM daily WHERE date < ?", (min(keep),)); con.commit()
        con.execute("VACUUM"); con.commit()
        log.info(f"정리: {n0:,} → {con.execute('SELECT count(*) FROM daily').fetchone()[0]:,}행 (최근 {len(keep)}거래일)")
d0, d1 = con.execute("SELECT min(date), max(date) FROM daily").fetchone()
log.info(f"코스닥 완료: {tot:,}행 반영 ({time.time()-t0:.0f}s) · DB "
         f"{con.execute('SELECT count(*) FROM daily').fetchone()[0]:,}행 {d0}~{d1}")
con.close()
