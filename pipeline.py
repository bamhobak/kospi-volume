"""
웹 배포용 파이프라인 (GitHub Actions / 로컬 공용)
  1) data/*.csv(월별 이력) → SQLite 복원
  2) 네이버에서 최근 15영업일 수집 (collect.main)
  3) SQLite → data/YYYY-MM.csv 재작성 (변경된 달만)
  4) site/ 정적 사이트 생성: index.html + data/table.json(전 종목 20영업일) + data/stock/{code}.json(60영업일)
사용: python pipeline.py [--wait] [--no-collect]
"""
import csv, json, shutil, sqlite3, sys
from pathlib import Path
import collect

BASE = Path(__file__).parent
DATA = BASE / "data"
SITE = BASE / "site"
TABLE_DAYS, STOCK_DAYS = 20, 300   # 스크리너: 1년(240)+2개월(40)+3거래일(3)
W_SURGE, W_QUIET, W_BASE = 3, 40, 240
COLS = ["date", "ticker", "name", "close", "change", "volume", "indiv", "organ", "frgn", "foreign_ratio"]

def restore_db():
    con = sqlite3.connect(collect.DB); collect.init_db(con)
    for f in sorted(DATA.glob("20??-??.csv")):
        with open(f, encoding="utf-8") as fh:
            rows = [tuple(r[c] or None for c in COLS) for r in csv.DictReader(fh)]
        con.executemany("INSERT OR IGNORE INTO daily VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit(); con.close()

def dump_csv():
    con = sqlite3.connect(collect.DB)
    months = [r[0] for r in con.execute("SELECT DISTINCT substr(date,1,6) FROM daily ORDER BY 1")]
    for m in months:
        rows = con.execute(f"SELECT {','.join(COLS)} FROM daily WHERE substr(date,1,6)=? ORDER BY date, ticker", (m,)).fetchall()
        out = DATA / f"{m[:4]}-{m[4:]}.csv"
        with open(out, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh); w.writerow(COLS); w.writerows(rows)
    con.close()

def build_site():
    (SITE / "data" / "stock").mkdir(parents=True, exist_ok=True)
    for f in (SITE / "data" / "stock").glob("*.json"): f.unlink()
    shutil.copy(BASE / "index.html", SITE / "index.html")
    con = sqlite3.connect(collect.DB); con.row_factory = sqlite3.Row
    dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily ORDER BY date DESC LIMIT ?", (STOCK_DAYS,))][::-1]
    if not dates:
        json.dump({"dates": [], "rows": [], "updated": ""}, open(SITE / "data" / "table.json", "w", encoding="utf-8")); return
    rows = con.execute("SELECT * FROM daily WHERE date >= ? ORDER BY ticker, date", (dates[0],)).fetchall()
    con.close()
    idx = {d: i for i, d in enumerate(dates)}
    by = {}
    for r in rows:
        s = by.setdefault(r["ticker"], {"ticker": r["ticker"], "name": r["name"], "rows": []})
        s["rows"].append([idx[r["date"]], r["close"], r["change"], r["volume"], r["indiv"], r["organ"], r["frgn"], r["foreign_ratio"]])
    tdates = dates[-TABLE_DAYS:]; t0 = len(dates) - len(tdates)
    table = []
    for s in by.values():
        m = {x[0]: x for x in s["rows"]}
        last = s["rows"][-1]
        vols = [m[t0 + i][3] if (t0 + i) in m else None for i in range(len(tdates))]
        inv = [[m[t0 + i][k] if (t0 + i) in m else 0 for i in range(len(tdates))] for k in (4, 5, 6)]
        # 스크리너용 평균: 급등창(최근 W_SURGE) / 잠잠창(그 이전 W_QUIET) / 기준창(그 이전 W_BASE)
        vol_all = [x[3] for x in s["rows"] if x[3] is not None]
        avg = lambda a: (sum(a) / len(a)) if a else None
        q0, b0 = W_SURGE + W_QUIET, W_SURGE + W_QUIET + W_BASE
        aw, a1, a6 = avg(vol_all[-W_SURGE:]), avg(vol_all[-q0:-W_SURGE]), avg(vol_all[-b0:-q0])
        n6 = len(vol_all[-b0:-q0])
        amt_all = [x[3] * x[1] for x in s["rows"] if x[3] is not None and x[1]]   # 거래대금(주×종가)
        amt1 = avg(amt_all[-q0:-W_SURGE])   # 잠잠창 일평균 거래대금(원)
        table.append({"t": s["ticker"], "n": s["name"], "c": last[1], "ch": last[2], "fr": last[7], "v": vols, "i": inv[0], "o": inv[1], "f": inv[2],
                      "aw": aw, "a1": a1, "a6": a6 if n6 >= W_BASE // 2 else None,
                      "amt": round(amt1 / 1e8, 2) if amt1 else None, "pref": s["ticker"][-1] != "0"})
        json.dump({"ticker": s["ticker"], "name": s["name"], "dates": dates, "rows": s["rows"]},
                  open(SITE / "data" / "stock" / f"{s['ticker']}.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump({"dates": tdates, "rows": table, "updated": collect.datetime.now().strftime("%Y-%m-%d %H:%M")},
              open(SITE / "data" / "table.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"site: {len(table)}종목, {tdates[0]}~{tdates[-1]}, table.json {round((SITE/'data'/'table.json').stat().st_size/1024)}KB")

if __name__ == "__main__":
    restore_db()
    if "--no-collect" not in sys.argv:
        if "--wait" in sys.argv: collect.wait_for_today()
        collect.main()
    dump_csv()
    build_site()
