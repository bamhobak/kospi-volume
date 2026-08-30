# -*- coding: utf-8 -*-
"""코스닥 수집 (2021-01-01 ~ 현재) — data/kosdaq.db 에 별도 저장
   메인 kospi.db 를 건드리지 않는다 (pipeline.py 가 market 필터 없이 daily 를 읽기 때문).
   (1) 시세 OHLCV: FinanceDataReader (수정주가)
   (2) 투자자 기관/외국인: 네이버 frgn 페이지 (20행/페이지)
사용: python collect_kosdaq.py price          # 시세만
      python collect_kosdaq.py inv [--min-amt 1]  # 투자자 (일평균 거래대금 N억 이상 종목만)
"""
import io, sqlite3, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import pandas as pd, requests
import FinanceDataReader as fdr
import collect

log = collect.log
BASE = Path(__file__).parent
DB = BASE / "data" / "kosdaq.db"
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
MODE = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "price"
FROM, TO = arg("--from", "2021-01-01"), arg("--to", time.strftime("%Y-%m-%d"))
FD, TD = FROM.replace("-", ""), TO.replace("-", "")
W = int(arg("--workers", "8"))
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

con = sqlite3.connect(DB, timeout=900)
con.execute("""CREATE TABLE IF NOT EXISTS daily(
    date TEXT, ticker TEXT, name TEXT, close INTEGER, change INTEGER, volume INTEGER,
    open INTEGER, high INTEGER, low INTEGER, market TEXT,
    indiv INTEGER, organ INTEGER, frgn INTEGER, foreign_ratio REAL, marcap REAL,
    PRIMARY KEY(date, ticker))""")
con.execute("CREATE INDEX IF NOT EXISTS ix_kd_ticker ON daily(ticker, date)")
con.execute("CREATE TABLE IF NOT EXISTS done(mode TEXT, ticker TEXT, n INTEGER, at TEXT, PRIMARY KEY(mode, ticker))")
if "--reset" in sys.argv:                      # 기간을 늘려 다시 받을 때
    con.execute("DELETE FROM done WHERE mode=?", (MODE,)); con.commit()
    log.info(f"done({MODE}) 초기화 — 전 종목 재수집")
con.commit()

listing = fdr.StockListing("KOSDAQ")
CODES = [(r.Code, r.Name) for r in listing.itertuples() if isinstance(r.Code, str) and len(r.Code) == 6]
log.info(f"코스닥 상장 {len(CODES)}종목 · {FROM} ~ {TO} · 모드 {MODE}")

# ── (1) 시세 ────────────────────────────────────────────────
UPS = ("INSERT INTO daily (date,ticker,name,close,change,volume,open,high,low,market) "
       "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(date,ticker) DO UPDATE SET "
       "name=excluded.name, close=excluded.close, change=excluded.change, volume=excluded.volume, "
       "open=excluded.open, high=excluded.high, low=excluded.low, market=excluded.market")

def price_one(code, name):
    try:
        d = fdr.DataReader(code, FROM, TO)
        if d is None or len(d) == 0: return []
        out, prev = [], None
        for dt_, r in d.iterrows():
            try:
                if not r["Close"] or pd.isna(r["Close"]): continue
                c = int(r["Close"]); ch = None if prev is None else c - prev; prev = c
                out.append((dt_.strftime("%Y%m%d"), code, name, c, ch, int(r["Volume"]),
                            int(r["Open"]), int(r["High"]), int(r["Low"]), "KOSDAQ"))
            except Exception: pass
        return out
    except Exception as e:
        log.warning(f"시세 {code}: {str(e)[:60]}"); return []

if MODE == "price":
    done = {r[0] for r in con.execute("SELECT ticker FROM done WHERE mode='price'")}
    todo = [(c, n) for c, n in CODES if c not in done]
    log.info(f"시세 대상 {len(todo)}종목 (완료 {len(done)})")
    n = tot = 0; t0 = time.time()
    with ThreadPoolExecutor(W) as ex:
        fut = {ex.submit(price_one, c, nm): c for c, nm in todo}
        for f in as_completed(fut):
            rows = f.result(); c = fut[f]
            if rows: con.executemany(UPS, rows); tot += len(rows)
            con.execute("INSERT OR REPLACE INTO done VALUES('price',?,?,?)",
                        (c, len(rows), time.strftime("%Y-%m-%d %H:%M")))
            n += 1
            if n % 100 == 0:
                con.commit(); log.info(f"시세 {n}/{len(todo)} ({tot:,}행, {time.time()-t0:.0f}s)")
    con.commit()
    log.info(f"시세 완료: {tot:,}행 ({time.time()-t0:.0f}s)")
    d0, d1 = con.execute("SELECT min(date), max(date) FROM daily").fetchone()
    log.info(f"DB: {con.execute('SELECT count(*) FROM daily').fetchone()[0]:,}행 · "
             f"{con.execute('SELECT count(DISTINCT ticker) FROM daily').fetchone()[0]}종목 · {d0}~{d1}")

# ── (2) 투자자 ──────────────────────────────────────────────
def inv_one(code):
    """frgn 페이지를 최신부터 훑어 FD 까지 수집 (20행/페이지)"""
    out = []; page = 1; miss = 0; prev_oldest = None
    while page <= 200:
        try:
            r = requests.get(f"https://finance.naver.com/item/frgn.naver?code={code}&page={page}",
                             headers=HDR, timeout=20); r.encoding = "euc-kr"
            tabs = [x for x in pd.read_html(io.StringIO(r.text)) if x.shape[1] >= 9 and x.shape[0] > 3]
            if not tabs: break
            t = tabs[0].dropna(how="all"); t.columns = range(t.shape[1])
            got = 0; oldest = None
            for _, row in t.iterrows():
                d = str(row[0]).replace(".", "")
                if not d.isdigit() or len(d) != 8: continue
                got += 1; oldest = d if oldest is None else min(oldest, d)
                if not (FD <= d <= TD): continue
                try:
                    out.append((int(float(row[5])), int(float(row[6])),
                                float(str(row[8]).replace("%", "")) if pd.notna(row[8]) else None, d, code))
                except Exception: pass
            if got == 0:
                miss += 1
                if miss >= 3: break
            else:
                miss = 0
                if oldest and oldest < FD: break
                if oldest is not None and oldest == prev_oldest: break   # 마지막 페이지 반복 반환
                prev_oldest = oldest
            page += 1
        except Exception as e:
            log.warning(f"투자자 {code} p{page}: {str(e)[:40]}"); time.sleep(2); page += 1
    return out

if MODE == "inv":
    MIN_AMT = float(arg("--min-amt", "1"))    # 일평균 거래대금 하한(억) — 거래 불가 종목 제외
    liq = [r[0] for r in con.execute(
        "SELECT ticker FROM daily WHERE volume>0 AND close>0 GROUP BY ticker "
        "HAVING avg(volume*close)/1e8 >= ?", (MIN_AMT,))]
    done = {r[0] for r in con.execute("SELECT ticker FROM done WHERE mode='inv'")}
    todo = [t for t in sorted(liq) if t not in done]
    log.info(f"투자자 대상 {len(todo)}종목 (거래대금 {MIN_AMT}억↑ {len(liq)}종목 중 완료 {len(done)})")
    n = tot = 0; t0 = time.time()
    with ThreadPoolExecutor(W) as ex:
        fut = {ex.submit(inv_one, c): c for c in todo}
        for f in as_completed(fut):
            rows = f.result(); c = fut[f]
            if rows:
                con.executemany("UPDATE daily SET organ=?, frgn=?, "
                                "foreign_ratio=COALESCE(foreign_ratio,?) WHERE date=? AND ticker=?", rows)
                tot += len(rows)
            con.execute("INSERT OR REPLACE INTO done VALUES('inv',?,?,?)",
                        (c, len(rows), time.strftime("%Y-%m-%d %H:%M")))
            n += 1
            if n % 50 == 0:
                con.commit()
                el = time.time() - t0
                log.info(f"투자자 {n}/{len(todo)} ({tot:,}행, {el:.0f}s, 남은 예상 {el/n*(len(todo)-n)/60:.0f}분)")
    con.commit()
    log.info(f"투자자 완료: {tot:,}행 ({time.time()-t0:.0f}s)")
    fill = con.execute("SELECT count(*) FROM daily WHERE frgn IS NOT NULL").fetchone()[0]
    log.info(f"외국인 채워진 행: {fill:,} / 전체 {con.execute('SELECT count(*) FROM daily').fetchone()[0]:,}")
con.close()
