"""1회성 과거 백필: (1) 거래량/종가 FDR 2024-10~2025-03, (2) 네이버 금융 외국인/기관 일별 페이지로 frgn/organ 채우기"""
import io, sqlite3, sys, time, logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests, pandas as pd
import FinanceDataReader as fdr
import collect

FROM = sys.argv[1] if len(sys.argv) > 1 else "20251201"   # 외국인 채울 시작일
HDR = {"User-Agent": "Mozilla/5.0"}
log = collect.log
listing = fdr.StockListing("KOSPI")[["Code", "Name"]]
if "--skip-fdr" in sys.argv: fdr_listing = listing.iloc[0:0]
else: fdr_listing = listing
con = sqlite3.connect(collect.DB); collect.init_db(con)

# (1) 거래량/종가 장기 백필
def fdr_one(code, name):
    rows = []
    try:
        df = fdr.DataReader(code, "2024-10-01", "2025-03-31"); prev = None
        for d, r in df.iterrows():
            c = int(r["Close"]); ch = None if prev is None else c - prev; prev = c
            rows.append((d.strftime("%Y%m%d"), code, name, c, ch, int(r["Volume"]), None, None, None, None))
    except Exception as e: log.warning(f"FDR {code} {name}: {e}")
    return rows
n = 0
with ThreadPoolExecutor(8 if "--skip-fdr" not in sys.argv else 0 or 1) as ex:
    for f in as_completed([ex.submit(fdr_one, c, nm) for c, nm in fdr_listing.itertuples(index=False)]):
        con.executemany("INSERT OR IGNORE INTO daily VALUES (?,?,?,?,?,?,?,?,?,?)", f.result()); n += 1
        if n % 200 == 0: con.commit(); log.info(f"FDR 진행 {n}/{len(listing)}")
con.commit(); log.info("FDR 백필 완료")

# (2) 외국인/기관 일별 (네이버 금융 frgn 페이지, 20행/페이지)
def frgn_one(code):
    out = []; page = 1
    while page <= 40:
        try:
            r = requests.get(f"https://finance.naver.com/item/frgn.naver?code={code}&page={page}", headers=HDR, timeout=15); r.encoding = "euc-kr"
            tabs = [t for t in pd.read_html(io.StringIO(r.text)) if t.shape[1] >= 9 and t.shape[0] > 3]
            if not tabs: break
            t = tabs[0].dropna(how="all"); t.columns = range(t.shape[1])
            got = 0
            for _, row in t.iterrows():
                d = str(row[0]).replace(".", "")
                if not d.isdigit() or len(d) != 8: continue
                got += 1
                if d < FROM: return out
                try: out.append((d, code, int(float(row[4])), int(float(row[5])), int(float(row[6])), float(str(row[8]).replace("%", "")) if pd.notna(row[8]) else None))
                except Exception: pass
            if got == 0: break
            page += 1
        except Exception as e:
            log.warning(f"frgn {code} p{page}: {e}"); time.sleep(2); page += 1
    return out
n = 0; total = 0
with ThreadPoolExecutor(4) as ex:
    for f in as_completed([ex.submit(frgn_one, c) for c, _ in listing.itertuples(index=False)]):
        rows = f.result()
        # frgn이 비어 있는 행만 채움 (volume/organ/frgn/ratio)
        con.executemany("UPDATE daily SET organ=?, frgn=?, foreign_ratio=COALESCE(foreign_ratio, ?) WHERE date=? AND ticker=? AND frgn IS NULL",
                        [(o, fr, ra, d, c) for d, c, v, o, fr, ra in rows])
        total += len(rows); n += 1
        if n % 100 == 0: con.commit(); log.info(f"외국인 진행 {n}/{len(listing)} ({total}행)")
con.commit()
print(con.execute("SELECT min(date), max(date), count(*), sum(frgn IS NOT NULL) FROM daily").fetchone())
print("frgn 있는 날짜 범위:", con.execute("SELECT min(date), max(date) FROM daily WHERE frgn IS NOT NULL").fetchone())
con.close()
