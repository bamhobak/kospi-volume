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

def upjong_ret60(con, up, dates, n=60):
    """업종 n일 수익률 = 소속 종목들의 n거래일 수익률 동일가중 평균 (회원 5종목 이상)
       백테스트(f3_sector.py)와 같은 정의 — 지수 누적이 아니라 종목별 수익률의 평균"""
    if len(dates) < n + 1 or not up: return {}
    d0, d1 = dates[-(n + 1)], dates[-1]
    px = {}
    for d, t, c in con.execute(
            "SELECT date, ticker, close FROM daily WHERE market='KOSPI' AND close>0 AND date IN (?,?)", (d0, d1)):
        px.setdefault(t, {})[d] = c
    byg = {}
    for t, s in px.items():
        g = up.get(t)
        if not g or g == "기타": continue
        a, b = s.get(d0), s.get(d1)
        if a and b: byg.setdefault(g, []).append((b / a - 1) * 100)
    return {g: round(sum(v) / len(v), 2) for g, v in byg.items() if len(v) >= 5}

def short_flags(dates):
    """최근 공매도 비중 5일평균 < 20일평균 여부 (short_recent.csv + kosdaq_short_recent.csv)"""
    by = {}
    for name in ("short_recent.csv", "kosdaq_short_recent.csv"):
        f = DATA / name
        if not f.exists(): continue
        with open(f, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                try: by.setdefault(r["ticker"], []).append((r["date"], float(r["short_ratio"])))
                except (TypeError, ValueError): pass
    if not by: return {}
    out = {}
    for t, v in by.items():
        v.sort()
        s5 = [x[1] for x in v[-5:]]; s20 = [x[1] for x in v[-20:]]
        if len(s5) < 5 or len(s20) < 20: continue
        a5, a20 = sum(s5) / len(s5), sum(s20) / len(s20)
        out[t] = {"sr5": round(a5, 2), "sr20": round(a20, 2), "srDown": a5 < a20}
    return out

INDUSTRY_CSV = DATA / "industry.csv"

VALUATION_CSV = DATA / "valuation.csv"

def load_valuation():
    """PER/PBR/PCR 등 (data/valuation.csv) — collect_valuation.py 가 하루 1회 갱신"""
    if not VALUATION_CSV.exists(): return {}
    out = {}
    with open(VALUATION_CSV, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            f = lambda k: (float(r[k]) if r.get(k) not in (None, "", "None") else None)
            try:
                out[r["ticker"]] = {"per": f("per"), "pbr": f("pbr"), "pcr": f("pcr"),
                                    "eps": f("eps"), "bps": f("bps"), "dy": f("div_yield"),
                                    "uper": f("upjong_per"), "ev": f("ev_ebitda")}
            except ValueError: pass
    return out

def load_industry():
    """표준산업분류 (코스닥 업종 조건용) — data/industry.csv"""
    if not INDUSTRY_CSV.exists(): return {}
    with open(INDUSTRY_CSV, encoding="utf-8") as fh:
        return {r["ticker"]: r["industry"] for r in csv.DictReader(fh) if r.get("industry")}

def fill_valuation(table):
    """PER/PBR/PCR 등을 종목 행에 붙인다."""
    V = load_valuation()
    n = 0
    for r in table:
        v = V.get(r["t"])
        if not v: continue
        r.update({k: x for k, x in v.items() if x is not None}); n += 1
    print(f"밸류에이션: {len(V):,}종목 로드 · {n:,}종목 매칭")

def fill_sr60(table, up_kospi=None, r60_kospi=None):
    """종목마다 '소속 업종의 60일 수익률'(sr60) 을 채운다.
       정의를 백테스트와 통일: **industry.csv(KRX 표준산업분류) + 소속 종목 60일 수익률의 중앙값**,
       코스피·코스닥 각각 자기 시장 안에서만 집계, 회원 5종목 미만 업종은 None.
       (예전에는 코스피만 sector.csv + 평균을 썼는데, 그러면 사이트와 백테스트 임계값이 어긋난다.
        규칙은 sr60 이 None 이면 '차단' 한다 — 업종을 모르는 종목이 최악 손실을 만들었기 때문.)"""
    IND = load_industry()
    agg = {"KOSPI": {}, "KOSDAQ": {}}
    for r in table:
        if r.get("ret60") is None: continue
        g = IND.get(r["t"])
        if not g or g == "기타": continue
        agg[r.get("mk") or "KOSPI"].setdefault(g, []).append(r["ret60"])
    med = {}
    for mk, by in agg.items():
        for g, v in by.items():
            if len(v) < 5: continue
            v = sorted(v); n = len(v)
            med[(mk, g)] = round(v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2, 2)
    n = 0
    for r in table:
        g = IND.get(r["t"])
        if g: r["up"] = r.get("up") or g
        r["sr60"] = med.get(((r.get("mk") or "KOSPI"), g))
        if r["sr60"] is not None: n += 1
    print(f"업종 60일 수익률(중앙값·회원5+): {len(med)}업종 · 종목 {n:,}개 매칭")

def load_kosdaq(dates):
    """코스닥 최근 구간 (data/kosdaq.db) — 없으면 빈 목록.
       코스닥 필터는 최근 60거래일이면 계산되므로 전체 이력을 커밋하지 않는다."""
    db = DATA / "kosdaq.db"
    if not db.exists(): return []
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=120)
        c.row_factory = sqlite3.Row
        r = c.execute("SELECT * FROM daily WHERE date >= ? ORDER BY ticker, date", (dates[0],)).fetchall()
        c.close()
        print(f"코스닥 {len(r):,}행 · {len({x['ticker'] for x in r})}종목")
        return list(r)
    except Exception as e:
        print("코스닥 로드 실패:", str(e)[:80]); return []

def ret2y_map(dates, back=500):
    """2년(기본 500거래일) 전 종가 대비 수익률 — 기준은 창의 첫 날이 아니라 **최신 거래일** — P4 의 '장기 과열 배제' 조건용.
       전체 창(STOCK_DAYS=300)을 늘리면 종목별 JSON 이 배로 커지므로,
       필요한 '그 시점 종가' 만 코스피/코스닥 DB 에서 따로 읽는다.
       그 날짜에 거래가 없던 종목은 전후 10거래일 중 가장 이른 값을 쓴다."""
    out = {}
    for db, ro in ((collect.DB, False), (DATA / "kosdaq.db", True)):
        try:
            if ro and not Path(db).exists(): continue
            c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=120)
            ds = [r[0] for r in c.execute(
                "SELECT DISTINCT date FROM daily WHERE date<=? ORDER BY date DESC LIMIT ?", (dates[-1], back))]
            if len(ds) < back * 0.8: c.close(); continue      # 이력이 짧으면 건너뜀(조건 통과 처리)
            lo = ds[-1]; hi = ds[max(len(ds) - 11, 0)]
            for t, d, cl in c.execute(
                    "SELECT ticker,date,close FROM daily WHERE date BETWEEN ? AND ? AND close>0 ORDER BY ticker,date",
                    (lo, hi)):
                if t not in out: out[t] = cl
            c.close()
        except Exception as e:
            print("2년 전 종가 조회 실패:", str(e)[:80])
    return out


def load_debt_ratio():
    """종목별 최신 '공시된' 부채비율 (data/dart/financials.db).
       공시 시차를 지켜 아직 공개되지 않은 분기는 쓰지 않는다(1·3분기·반기 +60일, 사업보고서 +105일).
       연결(CFS) 우선, 없으면 별도(OFS). 재무가 없으면 None → 규칙은 통과로 처리."""
    # 사이트(CI)에는 financials.db(181MB)가 없다 → collect_dart_fin.py 가 만든 스냅샷 CSV 를 먼저 본다
    snap = DATA / "debt_ratio.csv"
    if snap.exists():
        out = {}
        with open(snap, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                try: out[r["ticker"]] = float(r["debt_ratio"])
                except (TypeError, ValueError): pass
        if out:
            print(f"부채비율: {len(out):,}종목 (스냅샷 {snap.name})")
            return out
    f = DATA / "dart" / "financials.db"
    if not f.exists(): return {}
    END = {"11013": "0331", "11012": "0630", "11014": "0930", "11011": "1231"}
    LAG = {"11013": 60, "11012": 60, "11014": 60, "11011": 105}
    today = collect.datetime.now().strftime("%Y%m%d")
    try:
        c = sqlite3.connect(f"file:{f}?mode=ro", uri=True, timeout=300)
        rows = c.execute("""SELECT stock_code, year, reprt, fs_div,
              max(CASE WHEN account='자본총계' THEN amount END),
              max(CASE WHEN account='부채총계' THEN amount END)
            FROM fin GROUP BY stock_code, year, reprt, fs_div""").fetchall()
        c.close()
    except Exception as e:
        print("재무 로드 실패:", str(e)[:80]); return {}
    best = {}
    for sc, y, rp, fs, eq, dbt in rows:
        if not sc or eq is None or dbt is None or eq == 0: continue
        end = collect.datetime.strptime(f"{y}{END[rp]}", "%Y%m%d")
        av = (end + collect.timedelta(days=LAG[rp])).strftime("%Y%m%d")
        if av > today: continue                       # 아직 공시 전
        key = (av, 0 if fs == "CFS" else 1)
        if sc not in best or key > best[sc][0]:
            best[sc] = (key, round(dbt / abs(eq) * 100, 1))
    out = {k: v[1] for k, v in best.items()}
    print(f"부채비율: {len(out):,}종목 (공시 시차 반영)")
    return out


def load_pbr_dart():
    """DART 기준 PBR = 시가총액 / 자본총계. 발행주식수·자본총계 모두 '공시된' 값만 쓴다.
       (data/valuation.csv 의 pbr 은 FnGuide 현재 스냅샷이라 백테스트와 정의가 다르다 —
        규칙은 이 함수가 만드는 값을 쓴다.) 스냅샷 CSV 우선, 없으면 DB."""
    snap = DATA / "pbr_dart.csv"
    if snap.exists():
        out = {}
        with open(snap, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                try: out[r["ticker"]] = (float(r["shares"]), float(r["equity"]))
                except (TypeError, ValueError): pass
        if out:
            print(f"PBR 재료(주식수·자본총계): {len(out):,}종목")
            return out
    return {}


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

def buyback_flags(last_date):
    """마지막 거래일에 자사주 직접취득 결정을 공시한 종목 (data/buyback_recent.csv).
       P5 규칙: 진입은 '공시 다음 거래일 시가'로 실측했으므로 당일 공시만 켠다 —
       사이트는 18:30 에 갱신되고 사용자는 다음날 아침에 사므로 시점이 정확히 맞는다."""
    f = DATA / "buyback_recent.csv"
    if not f.exists(): return set()
    out = set()
    with open(f, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["rcept_dt"] == last_date: out.add(r["ticker"])
    return out

def insider_counts(dates, n=60):
    """최근 n거래일 안에 임원·주요주주 소유상황보고가 몇 건 있었나 (종목별).
       P7 규칙이 쓴다 — 정보 우위 주체가 움직인 종목만 남기는 필터.
       공시 전체 DB 는 러너에 없으므로 collect_daily_extra.py 가 받아 둔
       data/insider_recent.csv(최근 130일) 를 쓴다."""
    f = DATA / "insider_recent.csv"
    if not f.exists(): return {}
    lo = dates[max(0, len(dates) - n)]          # n거래일 전 날짜
    out = {}
    with open(f, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["rcept_dt"] >= lo:
                out[r["ticker"]] = out.get(r["ticker"], 0) + 1
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
    rows = list(rows) + load_kosdaq(dates)
    TRET = theme_returns(con, TH, dates[-1]) if TH else {}
    RS = upjong_rs(con, UP, dates) if UP else {}
    R60 = upjong_ret60(con, UP, dates) if UP else {}      # 업종 60일 수익률(3번 필터용)
    SF = short_flags(dates)
    DILU = dilution_flags(dates[-1])
    BB = buyback_flags(dates[-1])
    INS = insider_counts(dates)
    C2Y = ret2y_map(dates)
    DBT = load_debt_ratio()
    PB = load_pbr_dart()
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
        og_all = [x[5] for x in s["rows"] if x[3] is not None]     # 기관 순매수(같은 정렬)
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
        ret60 = round((closes[-1] / closes[-61] - 1) * 100, 2) if len(closes) >= 61 and closes[-61] else None  # 업종 60일 수익률 집계용
        # 기간 수익률 (1M=20 / 3M=60 / 6M=120 / 1Y=240 거래일) — 수정주가 기준
        def _r(n):
            return round((closes[-1] / closes[-(n + 1)] - 1) * 100, 2) if len(closes) >= n + 1 and closes[-(n + 1)] else None
        r1m, r3m, r6m, r1y = _r(20), _r(60), _r(120), _r(240)
        a20p = avg(vol_all[-21:-1])                          # 직전 20일(당일 제외) 평균 거래량
        vs1 = round(vol_all[-1] / a20p, 2) if len(vol_all) >= 21 and a20p else None   # 당일 거래량 배수
        v60, f60 = vol_all[-60:], fr_all[-60:]               # 외국인 60일 누적 순매수 비중(%)
        fw60 = (round(sum(x or 0 for x in f60) / sum(v60) * 100, 2)
                if len(v60) >= 55 and len(f60) >= 55 and sum(v60) else None)
        amt20 = round(avg(amt_all[-20:]) / 1e8, 2) if len(amt_all) >= 20 else None    # 20일 평균 거래대금(억)
        v20 = sum(vol_all[-20:])
        ow20 = (round(sum(x or 0 for x in og_all[-20:]) / v20 * 100, 2)      # 기관 20일 누적 순매수 비중(%)
                if len(vol_all) >= 20 and len(og_all) >= 20 and v20 else None)
        fw20 = (round(sum(x or 0 for x in fr_all[-20:]) / v20 * 100, 2)      # 외국인 20일 누적 순매수 비중(%) — P7
                if len(vol_all) >= 20 and len(fr_all) >= 20 and v20 else None)
        v60s, o60 = sum(v60), og_all[-60:]                                   # 기관 60일 누적 순매수 비중(%) — P7
        ow60 = (round(sum(x or 0 for x in o60) / v60s * 100, 2)
                if len(v60) >= 55 and len(o60) >= 55 and v60s else None)
        # 가격 불연속(액면분할·병합 등 미조정) 감지: 상하한가 ±30% 라 32% 초과 변동은 물리적으로 불가능
        rec = closes[-26:]
        disc = any(rec[i-1] and not (0.68 < rec[i] / rec[i-1] < 1.32) for i in range(1, len(rec)))
        # ── P4(조용한 신고가)용 지표 ────────────────────────────
        hi250 = max(closes[-250:]) if len(closes) >= 60 else None            # 52주 신고가
        fromhi = round((closes[-1] / hi250 - 1) * 100, 2) if hi250 else None  # 신고가 대비(%)
        f5 = fr_all[-5:]; v5 = vol_all[-5:]
        fw5 = (round(sum(x or 0 for x in f5) / sum(v5) * 100, 2)
               if len(f5) >= 5 and sum(v5) else None)                         # 외국인 5일 순매수 비중
        if len(closes) >= 21:
            dr = [closes[i] / closes[i-1] - 1 for i in range(len(closes) - 20, len(closes)) if closes[i-1]]
            mu = sum(dr) / len(dr) if dr else 0
            vol20 = round((sum((x - mu) ** 2 for x in dr) / len(dr)) ** 0.5 * 100, 2) if dr else None
        else: vol20 = None                                                    # 20일 일간변동성(%)
        c2y = C2Y.get(s["ticker"])
        ret2y = round((closes[-1] / c2y - 1) * 100, 2) if c2y else None       # 2년 수익률
        # 작전주 배제용: 최근 1년 중 20일선 위에서 보낸 날의 비율 + 1년 수익률.
        # 둘 다 극단이면(오래 눌림 없이 오르며 대폭 상승) 2023-04 SG증권 사태형 종목이다.
        ret250 = round((closes[-1] / closes[-251] - 1) * 100, 2) if len(closes) >= 251 and closes[-251] else None
        ma20 = avg(closes[-20:]) if len(closes) >= 20 else None
        dma20 = round((closes[-1] / ma20 - 1) * 100, 2) if ma20 else None   # 20일선 이격도(%)
        ma25 = avg(closes[-25:]) if len(closes) >= 25 else None
        dev25 = round((closes[-1] / ma25 - 1) * 100, 2) if ma25 else None   # 25일선 괴리율(%) — P6
        # 60일 최대낙폭: 최근 60거래일 각 시점의 '그 시점 기준 60일 고점 대비 되돌림' 중 최저.
        # 얼마나 깊게 무너졌는지를 잰다(20일선 이격이 재는 '속도'와 다른 축).
        mdd60 = None
        if len(closes) >= 90:
            worst = 0.0
            for i in range(len(closes) - 60, len(closes)):
                hi = max(closes[max(i - 59, 0):i + 1])
                if hi: worst = min(worst, (closes[i] / hi - 1) * 100)
            mdd60 = round(worst, 2)
        above20 = None
        if len(closes) >= 80:
            n = min(250, len(closes) - 19)
            hit = 0
            for i in range(len(closes) - n, len(closes)):
                ma = sum(closes[i - 19:i + 1]) / 20
                if closes[i] > ma: hit += 1
            above20 = round(hit / n * 100, 1)
        table.append({"t": s["ticker"], "n": s["name"], "c": last[1], "ch": last[2], "fr": last[7], "v": vols, "i": inv[0], "o": inv[1], "f": inv[2], "streak": streak, "ret3": ret3, "ret10": ret10,
                      "ret20": ret20, "ret60": ret60, "fromhi": fromhi, "fw5": fw5, "vol20": vol20, "ret2y": ret2y, "ret250": ret250, "above20": above20, "fw20": fw20, "ow60": ow60, "dev25": dev25, "dma20": dma20, "mdd60": mdd60, "r1m": r1m, "r3m": r3m, "r6m": r6m, "r1y": r1y, "vs1": vs1, "fw60": fw60, "amt20": amt20, "ow20": ow20, "disc": disc,
                      "aw": aw, "a1": a1, "a6": a6 if n6 >= W_BASE // 2 else None,
                      "amt": round(amt1 / 1e8, 2) if amt1 else None, "cap": s.get("cap"), "pref": s["ticker"][-1] != "0", "mk": s.get("mkt", "KOSPI"),
                      "up": UP.get(s["ticker"]), "rs": RS.get(UP.get(s["ticker"])),
                      "sr": (SF.get(s["ticker"]) or {}).get("sr5"),
                      "sr20": (SF.get(s["ticker"]) or {}).get("sr20"),
                      "srDown": (SF.get(s["ticker"]) or {}).get("srDown"),
                      "dilu": s["ticker"] in DILU,
                      "bb": s["ticker"] in BB,
                      "ins60": INS.get(s["ticker"], 0),
                      "dbt": DBT.get(s["ticker"]),
                      "pbrd": (lambda v: round(last[1] * v[0] / v[1], 3) if (v and v[1] and last[1]) else None)(PB.get(s["ticker"])),
                      "th": sorted(TH.get(s["ticker"], []), key=lambda g: -TRET.get(g, 0))[:6]})
        json.dump({"ticker": s["ticker"], "name": s["name"], "dates": dates, "rows": s["rows"]},
                  open(SITE / "data" / "stock" / f"{s['ticker']}.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    fill_sr60(table, UP, R60)
    fill_valuation(table)
    json.dump({"dates": tdates, "rows": table, "kospi": kospi_state(), "themeRet": TRET, "upjongRS": RS, "upjongRet60": R60, "shortN": len(SF), "diluN": len(DILU), "sectorSnap": SNAP, "updated": collect.datetime.now().strftime("%Y-%m-%d %H:%M")},
              open(SITE / "data" / "table.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"site: {len(table)}종목, {tdates[0]}~{tdates[-1]}, table.json {round((SITE/'data'/'table.json').stat().st_size/1024)}KB")

if __name__ == "__main__":
    restore_db()
    if "--no-collect" not in sys.argv:
        if "--wait" in sys.argv: collect.wait_for_today()
        collect.main()
    dump_csv()
    if "--no-site" not in sys.argv: build_site()
