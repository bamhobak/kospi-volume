# -*- coding: utf-8 -*-
"""2021년 이후 상장폐지 종목 시세 수집 (생존편향 측정용) → data/delisted_kd.db
   DART corpCode.xml 에는 있으나 현재 코스피·코스닥·코넥스 어디에도 없는 종목 = 폐지 후보
"""
import io, json, sqlite3, sys, time, zipfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import pandas as pd, requests
import FinanceDataReader as fdr
import collect

log = collect.log
BASE = Path(__file__).parent
DB = BASE / "data" / "delisted_kd.db"
FROM, TO = "2018-01-01", "2026-08-28"
KEY = [l.split("=", 1)[1].strip() for l in (BASE / ".env").read_text(encoding="utf-8").splitlines()
       if l.startswith("DART_API_KEY=")][0]

listed = set()
for m in ("KOSPI", "KOSDAQ", "KONEX"):
    listed |= set(x for x in fdr.StockListing(m).Code.dropna() if isinstance(x, str) and len(x) == 6)
r = requests.get("https://opendart.fss.or.kr/api/corpCode.xml", params={"crtfc_key": KEY}, timeout=120)
z = zipfile.ZipFile(io.BytesIO(r.content))
root = ET.fromstring(z.read(z.namelist()[0]).decode("utf-8"))
ALL = {}
for e in root.iter("list"):
    sc = (e.findtext("stock_code") or "").strip()
    if len(sc) == 6 and sc.isdigit(): ALL[sc] = (e.findtext("corp_name") or "").strip()
cand = sorted(set(ALL) - listed)
if "--reset" in sys.argv:
    con0 = sqlite3.connect(DB, timeout=600); con0.execute("DELETE FROM done"); con0.commit(); con0.close()
    log.info("done 초기화 — 2018년부터 재수집")
log.info(f"폐지 후보 {len(cand):,}종목 · {FROM}~{TO}")

con = sqlite3.connect(DB, timeout=600)
con.execute("""CREATE TABLE IF NOT EXISTS daily(
    date TEXT, ticker TEXT, name TEXT, close INTEGER, change INTEGER, volume INTEGER,
    open INTEGER, high INTEGER, low INTEGER, PRIMARY KEY(date, ticker))""")
con.execute("CREATE INDEX IF NOT EXISTS ix_dl_t ON daily(ticker, date)")
con.execute("CREATE TABLE IF NOT EXISTS done(ticker TEXT PRIMARY KEY, n INTEGER)")
con.commit()
done = {r[0] for r in con.execute("SELECT ticker FROM done")}
todo = [c for c in cand if c not in done]
log.info(f"수집 대상 {len(todo):,}종목 (완료 {len(done)})")

def one(code):
    try:
        d = fdr.DataReader(code, FROM, TO)
        if d is None or len(d) == 0: return code, []
        out, prev = [], None
        for dt_, x in d.iterrows():
            if not x["Close"] or pd.isna(x["Close"]): continue
            c = int(x["Close"]); ch = None if prev is None else c - prev; prev = c
            out.append((dt_.strftime("%Y%m%d"), code, ALL.get(code, code), c, ch,
                        int(x["Volume"]), int(x["Open"]), int(x["High"]), int(x["Low"])))
        return code, out
    except Exception:
        return code, []

n = tot = hit = 0; t0 = time.time()
with ThreadPoolExecutor(8) as ex:
    for f in as_completed([ex.submit(one, c) for c in todo]):
        code, rows = f.result()
        if rows:
            con.executemany(
                "INSERT INTO daily (date,ticker,name,close,change,volume,open,high,low) "
                "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(date,ticker) DO UPDATE SET "
                "name=excluded.name, close=excluded.close, change=excluded.change, "
                "volume=excluded.volume, open=excluded.open, high=excluded.high, low=excluded.low",
                rows)   # 이미 모은 organ/frgn 은 건드리지 않는다
            tot += len(rows); hit += 1
        con.execute("INSERT OR REPLACE INTO done VALUES (?,?)", (code, len(rows)))
        n += 1
        if n % 200 == 0:
            con.commit(); log.info(f"{n}/{len(todo)} · 시세있음 {hit}종목 · {tot:,}행 ({time.time()-t0:.0f}s)")
con.commit()
log.info(f"완료: {hit}종목 · {tot:,}행 ({time.time()-t0:.0f}s)")
d0, d1 = con.execute("SELECT min(date), max(date) FROM daily").fetchone()
last = con.execute("SELECT count(*) FROM (SELECT ticker, max(date) m FROM daily GROUP BY ticker) WHERE m < '20260801'").fetchone()[0]
log.info(f"DB {d0}~{d1} · 2026-08 이전에 거래 끊긴(=폐지 추정) 종목 {last}개")
con.close()
