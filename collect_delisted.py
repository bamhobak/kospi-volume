# -*- coding: utf-8 -*-
"""상장폐지 종목 데이터 수집 (생존편향 측정용) — data/delisted.db 에 별도 저장
   시세: FDR / 투자자: 네이버 frgn (폐지 시점까지 보관됨)
"""
import io, sqlite3, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd, requests
import FinanceDataReader as fdr
import collect

log = collect.log
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
FROM = "20180101"
d = pd.read_csv("data/delisted_kospi.csv", dtype=str)
targets = [(r.Symbol, str(r.Name), str(r.DelistingDate).replace("-", "")) for _, r in d.iterrows()]
log.info(f"폐지 종목 {len(targets)}개 수집 시작")

con = sqlite3.connect("data/delisted.db", timeout=600)
con.execute("""CREATE TABLE IF NOT EXISTS daily(
    date TEXT, ticker TEXT, name TEXT, close INTEGER, change INTEGER, volume INTEGER,
    organ INTEGER, frgn INTEGER, foreign_ratio REAL,
    open INTEGER, high INTEGER, low INTEGER, delist_date TEXT, PRIMARY KEY(date,ticker))""")
con.execute("CREATE INDEX IF NOT EXISTS ix_t ON daily(ticker,date)")
con.execute("CREATE TABLE IF NOT EXISTS done(ticker TEXT PRIMARY KEY, n INTEGER)")
con.commit()
done = {r[0] for r in con.execute("SELECT ticker FROM done")}
todo = [t for t in targets if t[0] not in done]

def price(code, name, dl):
    try:
        px = fdr.DataReader(code, "2018-01-01", f"{dl[:4]}-{dl[4:6]}-{dl[6:]}")
        if px is None or len(px) == 0: return []
        out, prev = [], None
        for dt_, r in px.iterrows():
            try:
                if not r["Close"] or pd.isna(r["Close"]): continue
                c = int(r["Close"]); ch = None if prev is None else c - prev; prev = c
                out.append((dt_.strftime("%Y%m%d"), code, name, c, ch, int(r["Volume"]),
                            int(r["Open"]), int(r["High"]), int(r["Low"]), dl))
            except Exception: pass
        return out
    except Exception as e:
        log.warning(f"시세 {code} {name}: {str(e)[:50]}"); return []

def inv(code, dl):
    out, page, prev_oldest = [], 1, None
    while page <= 200:
        try:
            r = requests.get(f"https://finance.naver.com/item/frgn.naver?code={code}&page={page}",
                             headers=HDR, timeout=20); r.encoding = "euc-kr"
            tabs = [t for t in pd.read_html(io.StringIO(r.text)) if t.shape[1] >= 9 and t.shape[0] > 3]
            if not tabs: break
            t = tabs[0].dropna(how="all"); t.columns = range(t.shape[1])
            got, oldest = 0, None
            for _, row in t.iterrows():
                ds = str(row[0]).replace(".", "")
                if not ds.isdigit() or len(ds) != 8: continue
                got += 1; oldest = ds if oldest is None else min(oldest, ds)
                if ds < FROM: continue
                try:
                    out.append((int(float(row[5])), int(float(row[6])),
                                float(str(row[8]).replace("%", "")) if pd.notna(row[8]) else None, ds, code))
                except Exception: pass
            if got == 0: break
            if oldest and oldest < FROM: break
            if oldest is not None and oldest == prev_oldest: break
            prev_oldest = oldest; page += 1
        except Exception as e:
            log.warning(f"투자자 {code} p{page}: {str(e)[:40]}"); time.sleep(2); page += 1
    return out

def one(code, name, dl):
    return code, price(code, name, dl), inv(code, dl)

n = tp = ti = 0; t0 = time.time()
with ThreadPoolExecutor(4) as ex:
    for f in as_completed([ex.submit(one, c, nm, dl) for c, nm, dl in todo]):
        code, prows, irows = f.result()
        if prows:
            con.executemany("INSERT OR IGNORE INTO daily (date,ticker,name,close,change,volume,open,high,low,delist_date)"
                            " VALUES (?,?,?,?,?,?,?,?,?,?)", prows); tp += len(prows)
        if irows:
            con.executemany("UPDATE daily SET organ=?, frgn=?, foreign_ratio=? WHERE date=? AND ticker=?", irows)
            ti += len(irows)
        con.execute("INSERT OR REPLACE INTO done VALUES (?,?)", (code, len(prows)))
        n += 1
        if n % 10 == 0:
            con.commit(); log.info(f"{n}/{len(todo)} (시세 {tp:,} · 투자자 {ti:,}, {time.time()-t0:.0f}s)")
con.commit()
r = con.execute("SELECT count(*),count(DISTINCT ticker),min(date),max(date),sum(frgn IS NOT NULL) FROM daily").fetchone()
print(f"폐지종목: {r[0]:,}행 · {r[1]}종목 · {r[2]}~{r[3]} · 외국인 {r[4]:,}행")
con.close()
