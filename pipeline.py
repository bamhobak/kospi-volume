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
COLS = ["date", "ticker", "name", "close", "change", "volume", "indiv", "organ", "frgn", "foreign_ratio",
        "open", "high", "low", "amount", "marcap", "shares"]

def restore_db():
    con = sqlite3.connect(collect.DB); collect.init_db(con)
    for f in sorted(DATA.glob("20??-??.csv")):
        with open(f, encoding="utf-8") as fh:
            rows = [tuple((r.get(c) or None) for c in COLS) for r in csv.DictReader(fh)]
        con.executemany(f"INSERT OR IGNORE INTO daily ({','.join(COLS)}) VALUES ({','.join('?'*len(COLS))})", rows)
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

def kospi_state():
    """코스피 종가 vs 5일 이동평균 (시장 필터 배지용)"""
    try:
        import FinanceDataReader as fdr
        k = fdr.DataReader("KS11", (collect.datetime.now() - collect.timedelta(days=60)).strftime("%Y-%m-%d"))
        k = k[k["Close"] > 0]
        close = float(k["Close"].iloc[-1]); ma5 = float(k["Close"].tail(5).mean()); ma20 = float(k["Close"].tail(20).mean())
        return {"date": k.index[-1].strftime("%Y%m%d"), "close": round(close, 2), "ma5": round(ma5, 2),
                "ma20": round(ma20, 2), "up": close > ma5, "up20": close > ma20}
    except Exception as e:
        print("kospi 조회 실패:", e); return None

def load_sector(con):
    """최신 스냅샷의 업종·테마 매핑 (없으면 빈 dict)"""
    try:
        snap = con.execute("SELECT max(snap) FROM sector").fetchone()[0]
    except Exception:
        return {}, {}, None
    if not snap: return {}, {}, None
    up = {r[0]: r[1] for r in con.execute("SELECT ticker, gname FROM sector WHERE snap=? AND kind='upjong'", (snap,))}
    th = {}
    for t, g in con.execute("SELECT ticker, gname FROM sector WHERE snap=? AND kind='theme'", (snap,)):
        th.setdefault(t, []).append(g)
    return up, th, snap

def theme_returns(con, th, last_date):
    """테마별 당일 평균 등락률 (자체 DB 종가로 계산)"""
    chg = {r[0]: (r[1] / (r[2] - r[1]) * 100) if r[2] and r[1] is not None and r[2] != r[1] else 0.0
           for r in con.execute("SELECT ticker, change, close FROM daily WHERE date=?", (last_date,))}
    agg = {}
    for t, gs in th.items():
        if t not in chg: continue
        for g in gs: agg.setdefault(g, []).append(chg[t])
    return {g: round(sum(v) / len(v), 2) for g, v in agg.items() if len(v) >= 3}

def build_site():
    (SITE / "data" / "stock").mkdir(parents=True, exist_ok=True)
    for f in (SITE / "data" / "stock").glob("*.json"): f.unlink()
    shutil.copy(BASE / "index.html", SITE / "index.html")
    for f in (BASE / "assets").glob("*"): shutil.copy(f, SITE / f.name)
    con = sqlite3.connect(collect.DB); con.row_factory = sqlite3.Row
    UP, TH, SNAP = load_sector(con)
    dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily ORDER BY date DESC LIMIT ?", (STOCK_DAYS,))][::-1]
    if not dates:
        json.dump({"dates": [], "rows": [], "updated": ""}, open(SITE / "data" / "table.json", "w", encoding="utf-8")); return
    rows = con.execute("SELECT * FROM daily WHERE date >= ? ORDER BY ticker, date", (dates[0],)).fetchall()
    TRET = theme_returns(con, TH, dates[-1]) if TH else {}
    con.close()
    idx = {d: i for i, d in enumerate(dates)}
    by = {}
    for r in rows:
        s = by.setdefault(r["ticker"], {"ticker": r["ticker"], "name": r["name"], "rows": []})
        s["rows"].append([idx[r["date"]], r["close"], r["change"], r["volume"], r["indiv"], r["organ"], r["frgn"], r["foreign_ratio"]])
        if r["marcap"]: s["cap"] = round(r["marcap"] / 1e8)
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
        # 1번 필터 연속 신호 일수: k일 전 기준으로 조건 충족 여부를 계산해 연속 True 개수
        fr_all = [x[6] for x in s["rows"] if x[3] is not None]     # 외국인 순매수(거래량 있는 행과 정렬 맞춤)
        def cond(k):
            v = vol_all[:len(vol_all) - k] if k else vol_all
            f = fr_all[:len(fr_all) - k] if k else fr_all
            am = amt_all[:len(amt_all) - k] if k else amt_all
            if len(v) < b0: return False
            aw_, a1_, a6_ = avg(v[-W_SURGE:]), avg(v[-q0:-W_SURGE]), avg(v[-b0:-q0])
            if not (aw_ and a1_ and a6_): return False
            f5 = f[-5:]
            if any(x is None for x in f5): return False
            f5s, v5 = sum(f5), sum(v[-5:])
            return (a1_ / a6_ < 0.5 and aw_ / a1_ >= 2 and f5s > 0 and f5s >= 0.02 * v5
                    and (avg(am[-q0:-W_SURGE]) or 0) >= 3e8 and s["ticker"][-1] == "0")
        streak = 0
        for k in range(0, 10):
            if cond(k): streak += 1
            else: break
        closes = [x[1] for x in s["rows"] if x[1]]
        ret3 = round((closes[-1] / closes[-4] - 1) * 100, 2) if len(closes) >= 4 and closes[-4] else None   # 최근 3거래일 주가 변화율
        ret10 = round((closes[-1] / closes[-11] - 1) * 100, 2) if len(closes) >= 11 and closes[-11] else None  # 최근 10거래일
        table.append({"t": s["ticker"], "n": s["name"], "c": last[1], "ch": last[2], "fr": last[7], "v": vols, "i": inv[0], "o": inv[1], "f": inv[2], "streak": streak, "ret3": ret3, "ret10": ret10,
                      "aw": aw, "a1": a1, "a6": a6 if n6 >= W_BASE // 2 else None,
                      "amt": round(amt1 / 1e8, 2) if amt1 else None, "cap": s.get("cap"), "pref": s["ticker"][-1] != "0",
                      "up": UP.get(s["ticker"]), "th": sorted(TH.get(s["ticker"], []), key=lambda g: -TRET.get(g, 0))[:6]})
        json.dump({"ticker": s["ticker"], "name": s["name"], "dates": dates, "rows": s["rows"]},
                  open(SITE / "data" / "stock" / f"{s['ticker']}.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump({"dates": tdates, "rows": table, "kospi": kospi_state(), "themeRet": TRET, "sectorSnap": SNAP, "updated": collect.datetime.now().strftime("%Y-%m-%d %H:%M")},
              open(SITE / "data" / "table.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"site: {len(table)}종목, {tdates[0]}~{tdates[-1]}, table.json {round((SITE/'data'/'table.json').stat().st_size/1024)}KB")

if __name__ == "__main__":
    restore_db()
    if "--no-collect" not in sys.argv:
        if "--wait" in sys.argv: collect.wait_for_today()
        collect.main()
    dump_csv()
    if "--no-site" not in sys.argv: build_site()
