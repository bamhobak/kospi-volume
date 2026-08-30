# -*- coding: utf-8 -*-
"""상장폐지 코스닥 종목의 투자자(외국인/기관) 수집 → data/delisted_kd.db
   대상: data/kosdaq_delisted.csv (스팩 제외한 코스닥 주권 보통주 폐지 종목)
"""
import io, sqlite3, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import pandas as pd, requests
import collect

log = collect.log
BASE = Path(__file__).parent
DB = BASE / "data" / "delisted_kd.db"
FD, TD = "20210101", "20260828"
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
W = 8

con = sqlite3.connect(DB, timeout=900)
cols = {r[1] for r in con.execute("PRAGMA table_info(daily)")}
for c in ("organ", "frgn", "foreign_ratio"):
    if c not in cols:
        con.execute(f"ALTER TABLE daily ADD COLUMN {c} {'REAL' if c=='foreign_ratio' else 'INTEGER'}")
con.execute("CREATE TABLE IF NOT EXISTS inv_done(ticker TEXT PRIMARY KEY, n INTEGER)")
con.commit()
todo = [t for t in pd.read_csv("data/kosdaq_delisted.csv", dtype=str).Symbol
        if t not in {r[0] for r in con.execute("SELECT ticker FROM inv_done")}]
log.info(f"폐지 코스닥 투자자 수집: {len(todo)}종목")

def one(code):
    out = []; page = 1; miss = 0; prev = None
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
                if oldest is not None and oldest == prev: break
                prev = oldest
            page += 1
        except Exception:
            time.sleep(2); page += 1
    return code, out

n = tot = 0; t0 = time.time()
with ThreadPoolExecutor(W) as ex:
    for f in as_completed([ex.submit(one, c) for c in todo]):
        code, rows = f.result()
        if rows:
            con.executemany("UPDATE daily SET organ=?, frgn=?, foreign_ratio=COALESCE(foreign_ratio,?) "
                            "WHERE date=? AND ticker=?", rows)
            tot += len(rows)
        con.execute("INSERT OR REPLACE INTO inv_done VALUES (?,?)", (code, len(rows)))
        n += 1
        if n % 20 == 0:
            con.commit(); log.info(f"{n}/{len(todo)} ({tot:,}행, {time.time()-t0:.0f}s)")
con.commit()
fill = con.execute("SELECT count(*) FROM daily WHERE frgn IS NOT NULL").fetchone()[0]
log.info(f"완료: {tot:,}행 · 외국인 채워진 행 {fill:,} ({time.time()-t0:.0f}s)")
con.close()
