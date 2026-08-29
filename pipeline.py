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
        "open", "high", "low", "amount", "marcap", "shares", "market"]

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
        k = fdr.DataReader("KS11", (collect.datetime.now() - collect.timedelta(days=200)).strftime("%Y-%m-%d"))
        k = k[k["Close"] > 0]
        close = float(k["Close"].iloc[-1]); ma5 = float(k["Close"].tail(5).mean()); ma20 = float(k["Close"].tail(20).mean())
        ma60 = float(k["Close"].tail(60).mean()) if len(k) >= 60 else None
        out = {"date": k.index[-1].strftime("%Y%m%d"), "close": round(close, 2), "ma5": round(ma5, 2),
               "ma20": round(ma20, 2), "up": close > ma5, "up20": close > ma20,
               "ma60": round(ma60, 2) if ma60 else None, "up60": (close > ma60) if ma60 else None}
        try:
            q = fdr.DataReader("KQ11", (collect.datetime.now() - collect.timedelta(days=60)).strftime("%Y-%m-%d"))
            q = q[q["Close"] > 0]
            qc = float(q["Close"].iloc[-1]); q20 = float(q["Close"].tail(20).mean()); q5 = float(q["Close"].tail(5).mean())
            out.update(kq=round(qc, 2), kq20=round(q20, 2), kqUp20=qc > q20, kqUp5=qc > q5)
        except Exception as e:
            print("코스닥 지수 조회 실패:", e)
        return out
    except Exception as e:
        print("kospi 조회 실패:", e); return None

SECTOR_CSV = DATA / "sector.csv"

def load_sector(con):
    """업종·테마 매핑. DB의 최신 스냅샷을 쓰되, 없으면 커밋된 data/sector.csv 로 대체.
       (GitHub Actions 는 매 실행마다 DB를 CSV에서 새로 만들기 때문에 sector 테이블이 비어 있음)"""
    snap, rows = None, []
    try:
        snap = con.execute("SELECT max(snap) FROM sector").fetchone()[0]
    except Exception:
        snap = None
    if snap:
        rows = list(con.execute("SELECT kind, gname, ticker FROM sector WHERE snap=?", (snap,)))
        # DB에 있으면 CSV로도 남겨 다음 CI 실행에서 쓰게 함
        try:
            with open(SECTOR_CSV, "w", encoding="utf-8", newline="") as fh:
                w = csv.writer(fh); w.writerow(["snap", "kind", "gname", "ticker"])
                w.writerows([(snap, k, g, t) for k, g, t in rows])
        except Exception as e:
            print("sector.csv 쓰기 실패:", e)
    elif SECTOR_CSV.exists():
        with open(SECTOR_CSV, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                snap = r["snap"]; rows.append((r["kind"], r["gname"], r["ticker"]))
        print(f"sector: DB 비어 있음 → {SECTOR_CSV.name} 사용 ({len(rows):,}행, snap={snap})")
    if not rows: return {}, {}, None
    up = {t: g for k, g, t in rows if k == "upjong"}
    th = {}
    for k, g, t in rows:
        if k == "theme": th.setdefault(t, []).append(g)
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

def upjong_rs(con, up, dates):
    """업종 상대강도 = 업종 20일 수익률 - 시장(코스피 동일가중) 20일 수익률"""
    ds = dates[-21:]
    if len(ds) < 21 or not up: return {}
    px = {}
    for d, t, c in con.execute(
            "SELECT date, ticker, close FROM daily WHERE market='KOSPI' AND close IS NOT NULL "
            "AND date IN (%s)" % ",".join("?" * len(ds)), ds):
        px.setdefault(t, {})[d] = c
    gret, mret = {}, {}
    for t, series in px.items():
        g = up.get(t); prev = None
        for d in ds:
            c = series.get(d)
            if c is None: prev = None; continue
            if prev:
                r = (c / prev - 1) * 100
                mret.setdefault(d, []).append(r)
                if g and g != "기타": gret.setdefault(g, {}).setdefault(d, []).append(r)
            prev = c
    def cum(daily):
        x = 1.0
        for v in daily: x *= 1 + v / 100
        return (x - 1) * 100
    if not mret: return {}
    mk = cum([sum(v) / len(v) for _, v in sorted(mret.items())])
    return {g: round(cum([sum(v) / len(v) for _, v in sorted(dd.items())]) - mk, 2)
            for g, dd in gret.items() if len(dd) >= 15}

def short_flags(dates):
    """최근 공매도 비중 5일평균 < 20일평균 여부 (data/short_recent.csv)"""
    f = DATA / "short_recent.csv"
    if not f.exists(): return {}
    by = {}
    with open(f, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try: by.setdefault(r["ticker"], []).append((r["date"], float(r["short_ratio"])))
            except (TypeError, ValueError): pass
    out = {}
    for t, v in by.items():
        v.sort()
        s5 = [x[1] for x in v[-5:]]; s20 = [x[1] for x in v[-20:]]
        if len(s5) < 5 or len(s20) < 20: continue
        a5, a20 = sum(s5) / len(s5), sum(s20) / len(s20)
        out[t] = {"sr5": round(a5, 2), "sr20": round(a20, 2), "srDown": a5 < a20}
    return out

def dilution_flags(last_date, days=90):
    """최근 days일 내 유상증자·CB 공시 종목 (data/dilution_recent.csv)"""
    f = DATA / "dilution_recent.csv"
    if not f.exists(): return set()
    d0 = (collect.datetime.strptime(last_date, "%Y%m%d") - collect.timedelta(days=days)).strftime("%Y%m%d")
    out = set()
    with open(f, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if d0 <= r["rcept_dt"] <= last_date: out.add(r["ticker"])
    return out

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
    RS = upjong_rs(con, UP, dates) if UP else {}
    SF = short_flags(dates)
    DILU = dilution_flags(dates[-1])
    con.close()
    idx = {d: i for i, d in enumerate(dates)}
    by = {}
    for r in rows:
        s = by.setdefault(r["ticker"], {"ticker": r["ticker"], "name": r["name"], "rows": [], "mkt": r["market"] or "KOSPI"})
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
        # ── 3번 필터(폭락 반등)용 ──────────────────────────────
        ret20 = round((closes[-1] / closes[-21] - 1) * 100, 2) if len(closes) >= 21 and closes[-21] else None  # 최근 20거래일
        a20p = avg(vol_all[-21:-1])                          # 직전 20일(당일 제외) 평균 거래량
        vs1 = round(vol_all[-1] / a20p, 2) if len(vol_all) >= 21 and a20p else None   # 당일 거래량 배수
        v60, f60 = vol_all[-60:], fr_all[-60:]               # 외국인 60일 누적 순매수 비중(%)
        fw60 = (round(sum(x or 0 for x in f60) / sum(v60) * 100, 2)
                if len(v60) >= 60 and len(f60) >= 60 and sum(v60) else None)
        amt20 = round(avg(amt_all[-20:]) / 1e8, 2) if len(amt_all) >= 20 else None    # 20일 평균 거래대금(억)
        # 가격 불연속(액면분할·병합 등 미조정) 감지: 상하한가 ±30% 라 32% 초과 변동은 물리적으로 불가능
        rec = closes[-26:]
        disc = any(rec[i-1] and not (0.68 < rec[i] / rec[i-1] < 1.32) for i in range(1, len(rec)))
        table.append({"t": s["ticker"], "n": s["name"], "c": last[1], "ch": last[2], "fr": last[7], "v": vols, "i": inv[0], "o": inv[1], "f": inv[2], "streak": streak, "ret3": ret3, "ret10": ret10,
                      "ret20": ret20, "vs1": vs1, "fw60": fw60, "amt20": amt20, "disc": disc,
                      "aw": aw, "a1": a1, "a6": a6 if n6 >= W_BASE // 2 else None,
                      "amt": round(amt1 / 1e8, 2) if amt1 else None, "cap": s.get("cap"), "pref": s["ticker"][-1] != "0", "mk": s.get("mkt", "KOSPI"),
                      "up": UP.get(s["ticker"]), "rs": RS.get(UP.get(s["ticker"])),
                      "sr": (SF.get(s["ticker"]) or {}).get("sr5"),
                      "srDown": (SF.get(s["ticker"]) or {}).get("srDown"),
                      "dilu": s["ticker"] in DILU,
                      "th": sorted(TH.get(s["ticker"], []), key=lambda g: -TRET.get(g, 0))[:6]})
        json.dump({"ticker": s["ticker"], "name": s["name"], "dates": dates, "rows": s["rows"]},
                  open(SITE / "data" / "stock" / f"{s['ticker']}.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump({"dates": tdates, "rows": table, "kospi": kospi_state(), "themeRet": TRET, "upjongRS": RS, "shortN": len(SF), "diluN": len(DILU), "sectorSnap": SNAP, "updated": collect.datetime.now().strftime("%Y-%m-%d %H:%M")},
              open(SITE / "data" / "table.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"site: {len(table)}종목, {tdates[0]}~{tdates[-1]}, table.json {round((SITE/'data'/'table.json').stat().st_size/1024)}KB")

if __name__ == "__main__":
    restore_db()
    if "--no-collect" not in sys.argv:
        if "--wait" in sys.argv: collect.wait_for_today()
        collect.main()
    dump_csv()
    if "--no-site" not in sys.argv: build_site()
