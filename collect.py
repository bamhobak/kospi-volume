"""
코스피 전 종목 일별 거래량 + 투자자별(개인/기관/외국인) 순매수 수집기
- 데이터원: 네이버 증권 모바일 API (m.stock.naver.com/api/stock/{code}/trend), 종목 목록은 FinanceDataReader
- 매일 18:30 실행 → 당일까지 수집 (당일 투자자 수치는 잠정치, 다음날 재수집 시 확정치로 덮어씀) (최근 LOOKBACK 영업일 범위 누락분 자동 보충)
- 저장: data/kospi.db (SQLite), data/kospi_volume.csv
"""
import sqlite3, sys, time, logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import requests
import FinanceDataReader as fdr

BASE = Path(__file__).parent
DATA = BASE / "data"; DATA.mkdir(exist_ok=True)
DB = DATA / "kospi.db"
CSV = DATA / "kospi_volume.csv"
LOG = BASE / "collect.log"
PAGE_SIZE = 15       # 최근 N영업일 (누락 보충 범위)
KEEP_DAYS = 0         # 0 = 삭제 안 함. 과거 데이터는 백테스트 자산이므로 절대 지우지 않는다
                      # (2500일이었을 때 GitHub Actions 가 매일 2018~2019 데이터를 CSV에서 지우고 있었음)
WORKERS = 8
HDR = {"User-Agent": "Mozilla/5.0"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.FileHandler(LOG, encoding="utf-8"), logging.StreamHandler(sys.stdout)])
log = logging.getLogger("collect")
logging.getLogger("urllib3").setLevel(logging.WARNING)

EXTRA_COLS = [("open", "INTEGER"), ("high", "INTEGER"), ("low", "INTEGER"),
              ("amount", "INTEGER"), ("marcap", "INTEGER"), ("shares", "INTEGER"),
              ("market", "TEXT")]

def init_db(con):
    con.execute("""CREATE TABLE IF NOT EXISTS daily(
        date TEXT, ticker TEXT, name TEXT,
        close INTEGER, change INTEGER, volume INTEGER,
        indiv INTEGER, organ INTEGER, frgn INTEGER, foreign_ratio REAL,
        PRIMARY KEY(date, ticker))""")
    con.execute("CREATE INDEX IF NOT EXISTS ix_daily_ticker ON daily(ticker, date)")
    have = {r[1] for r in con.execute("PRAGMA table_info(daily)")}
    for c, t in EXTRA_COLS:
        if c not in have: con.execute(f"ALTER TABLE daily ADD COLUMN {c} {t}")
    con.commit()

def num(s):
    if s is None: return None
    s = str(s).replace(",", "").replace("+", "").replace("%", "").strip()
    try: return float(s) if "." in s else int(s)
    except ValueError: return None

def fetch_one(code, name, cutoff):
    url = f"https://m.stock.naver.com/api/stock/{code}/trend?pageSize={PAGE_SIZE}&page=1"
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HDR, timeout=10); r.raise_for_status()
            rows = []
            for it in r.json():
                d = it["bizdate"]
                if d < cutoff: continue
                rows.append((d, code, name, num(it["closePrice"]), num(it["compareToPreviousClosePrice"]),
                             num(it["accumulatedTradingVolume"]), num(it["individualPureBuyQuant"]),
                             num(it["organPureBuyQuant"]), num(it["foreignerPureBuyQuant"]), num(it["foreignerHoldRatio"])))
            return rows
        except Exception as e:
            if attempt == 2: log.warning(f"{code} {name} 실패: {e}")
            time.sleep(2)
    return []

def export_csv(con):
    df = pd.read_sql("SELECT date, ticker, name, volume FROM daily", con)
    if df.empty: return
    recent = sorted(df["date"].unique())[-7:]
    pv = df[df["date"].isin(recent)].pivot_table(index=["ticker", "name"], columns="date", values="volume").reset_index()
    pv.to_csv(CSV, index=False, encoding="utf-8-sig")
    log.info(f"CSV 저장: {CSV} ({len(pv)}종목 x {len(recent)}일: {recent[0]}~{recent[-1]})")

def wait_for_today(deadline="21:00", interval=600):
    """네이버에 당일 투자자 데이터 행이 올라올 때까지 대기 (평일만, deadline까지)"""
    today = datetime.today()
    if today.weekday() >= 5: return
    ts = today.strftime("%Y%m%d")
    while datetime.now().strftime("%H:%M") < deadline:
        try:
            d = requests.get("https://m.stock.naver.com/api/stock/005930/trend?pageSize=1&page=1", headers=HDR, timeout=10).json()[0]
            if d["bizdate"] == ts:
                log.info(f"당일({ts}) 데이터 반영 확인 → 수집 시작"); return
            log.info(f"당일 데이터 아직 없음(최신 {d['bizdate']}), {interval//60}분 후 재확인")
        except Exception as e:
            log.warning(f"확인 실패: {e}")
        time.sleep(interval)
    log.warning("마감시각까지 당일 데이터 미반영 → 직전 데이터만 수집")

def get_listing():
    """KOSPI 종목 목록: FDR(KRX) 60초 제한, 실패 시 DB의 최근 종목 목록으로 대체"""
    from concurrent.futures import ThreadPoolExecutor as _TPE, TimeoutError as _TO
    try:
        with _TPE(1) as ex:
            return ex.submit(lambda: fdr.StockListing("KOSPI")).result(timeout=60)
    except Exception as e:
        log.warning(f"종목 목록(FDR) 실패 → DB 목록 사용: {e}")
        con = sqlite3.connect(DB); init_db(con)
        rows = con.execute("SELECT ticker, name FROM daily WHERE date=(SELECT max(date) FROM daily)").fetchall(); con.close()
        return pd.DataFrame(rows, columns=["Code", "Name"])

def apply_snapshot(con, listing, date):
    """StockListing 스냅샷(OHLC·거래대금·시총·상장주식수)을 해당 날짜 행에 반영"""
    cols = {"Open": "open", "High": "high", "Low": "low", "Amount": "amount", "Marcap": "marcap", "Stocks": "shares"}
    have = [c for c in cols if c in listing.columns]
    if not have: return 0
    rows = []
    for r in listing.itertuples(index=False):
        d = getattr(r, "_asdict", None)
        vals = []
        for c in have:
            v = getattr(r, c, None)
            try: vals.append(int(v) if v == v and v is not None else None)
            except Exception: vals.append(None)
        rows.append(tuple(vals) + (date, r.Code))
    sets = ", ".join(f"{cols[c]}=COALESCE(?, {cols[c]})" for c in have)
    con.executemany(f"UPDATE daily SET {sets} WHERE date=? AND ticker=?", rows)
    con.commit()
    return len(rows)

def main(progress=None):
    today = datetime.today()
    yesterday = today.strftime("%Y%m%d")  # 당일 포함
    log.info(f"수집 시작: ~{yesterday}")
    listing = get_listing()
    log.info(f"코스피 종목 수: {len(listing)}")
    con = sqlite3.connect(DB); init_db(con)
    total = done = 0
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = [ex.submit(fetch_one, r.Code, r.Name, "00000000") for r in listing.itertuples(index=False)]
        for f in as_completed(futs):
            rows = [r for r in f.result() if r[0] <= yesterday]
            if rows:
                con.executemany("INSERT INTO daily (date, ticker, name, close, change, volume, indiv, organ, frgn, foreign_ratio) VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(date, ticker) DO UPDATE SET name=excluded.name, close=excluded.close, change=excluded.change, volume=excluded.volume, indiv=excluded.indiv, organ=excluded.organ, frgn=excluded.frgn, foreign_ratio=excluded.foreign_ratio", rows); total += len(rows)
            done += 1
            if progress: progress(done, len(listing))
            if done % 200 == 0:
                con.commit(); log.info(f"진행 {done}/{len(listing)}")
    con.commit()
    try:
        n = apply_snapshot(con, listing, yesterday)
        log.info(f"시세 스냅샷 반영({yesterday}): {n}종목 (OHLC·거래대금·시총·상장주식수)")
    except Exception as e:
        log.warning(f"스냅샷 반영 실패: {e}")
    if KEEP_DAYS > 0:
        cutoff = (today - timedelta(days=KEEP_DAYS)).strftime("%Y%m%d")
        con.execute("DELETE FROM daily WHERE date < ?", (cutoff,)); con.commit()
    dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily ORDER BY date DESC LIMIT 7")]
    log.info(f"저장 {total}행, 최근 수집일: {dates}")
    export_csv(con); con.close()
    log.info("완료")

def backfill(start="2026-01-01"):
    """1회성 과거 백필: 거래량/종가는 FDR(장기), 투자자는 네이버 60일. 기존 행은 덮어쓰지 않음."""
    global PAGE_SIZE
    listing = get_listing()
    con = sqlite3.connect(DB); init_db(con)
    log.info(f"백필 시작 {start}~ ({len(listing)}종목)")
    def one(code, name):
        rows = []
        try:
            df = fdr.DataReader(code, start)
            prev = None
            for d, r in df.iterrows():
                close = int(r["Close"]); chg = None if prev is None else close - prev; prev = close
                rows.append((d.strftime("%Y%m%d"), code, name, close, chg, int(r["Volume"]), None, None, None, None))
        except Exception as e:
            log.warning(f"{code} {name} FDR 실패: {e}")
        return rows
    done = 0
    with ThreadPoolExecutor(WORKERS) as ex:
        for f in as_completed([ex.submit(one, r.Code, r.Name) for r in listing.itertuples(index=False)]):
            con.executemany("INSERT OR IGNORE INTO daily (date, ticker, name, close, change, volume, indiv, organ, frgn, foreign_ratio) VALUES (?,?,?,?,?,?,?,?,?,?)", f.result()); done += 1
            if done % 200 == 0: con.commit(); log.info(f"FDR 진행 {done}/{len(listing)}")
    con.commit()
    # 투자자 60일: 기존 행에 채워넣기
    PAGE_SIZE = 60
    done = 0
    with ThreadPoolExecutor(WORKERS) as ex:
        for f in as_completed([ex.submit(fetch_one, r.Code, r.Name, "00000000") for r in listing.itertuples(index=False)]):
            con.executemany("INSERT INTO daily (date, ticker, name, close, change, volume, indiv, organ, frgn, foreign_ratio) VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(date, ticker) DO UPDATE SET name=excluded.name, close=excluded.close, change=excluded.change, volume=excluded.volume, indiv=excluded.indiv, organ=excluded.organ, frgn=excluded.frgn, foreign_ratio=excluded.foreign_ratio", f.result()); done += 1
            if done % 200 == 0: con.commit(); log.info(f"투자자 진행 {done}/{len(listing)}")
    con.commit()
    n, d0, d1 = con.execute("SELECT count(*), min(date), max(date) FROM daily").fetchone()
    log.info(f"백필 완료: {n}행 {d0}~{d1}"); con.close()

if __name__ == "__main__":
    if "--backfill" in sys.argv: backfill(); sys.exit()
    if "--wait" in sys.argv: wait_for_today()
    main()
