# -*- coding: utf-8 -*-
"""코스피 과거 백필: 2018-01-01 ~ 2022-12-31
   (1) 시세 OHLCV: FinanceDataReader (수정주가)
   (2) 투자자 기관/외국인/외국인보유율: 네이버 frgn 페이지 (개인은 제공 안 함)
사용: python backfill_2018.py [--from 2018-01-01] [--to 2022-12-31] [--price-only|--inv-only]
"""
import io, sqlite3, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd, requests
import FinanceDataReader as fdr
import collect

log = collect.log
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
FROM, TO = arg("--from", "2018-01-01"), arg("--to", "2022-12-31")
FD, TD = FROM.replace("-", ""), TO.replace("-", "")
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

con = sqlite3.connect(collect.DB, timeout=600)
collect.init_db(con)
codes = con.execute("SELECT ticker, name FROM daily WHERE market='KOSPI' "
                    "GROUP BY ticker HAVING max(date)=(SELECT max(date) FROM daily)").fetchall()
if not codes:
    codes = con.execute("SELECT ticker, max(name) FROM daily GROUP BY ticker").fetchall()
log.info(f"코스피 {len(codes)}종목 · {FROM} ~ {TO}")

# ── (1) 시세 ────────────────────────────────────────────────
BC = "date, ticker, name, close, change, volume, open, high, low, market"
UPS = (f"INSERT INTO daily ({BC}) VALUES ({','.join('?'*10)}) "
       "ON CONFLICT(date,ticker) DO UPDATE SET name=excluded.name, close=excluded.close, "
       "change=excluded.change, volume=excluded.volume, open=excluded.open, "
       "high=excluded.high, low=excluded.low, market=excluded.market")
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
                            int(r["Open"]), int(r["High"]), int(r["Low"]), "KOSPI"))
            except Exception: pass
        return out
    except Exception as e:
        log.warning(f"시세 {code}: {str(e)[:60]}"); return []

if "--inv-only" not in sys.argv:
    n = tot = 0; t0 = time.time()
    with ThreadPoolExecutor(8) as ex:
        for f in as_completed([ex.submit(price_one, c, nm) for c, nm in codes]):
            rows = f.result()
            if rows: con.executemany(UPS, rows); tot += len(rows)
            n += 1
            if n % 100 == 0:
                con.commit(); log.info(f"시세 {n}/{len(codes)} ({tot:,}행, {time.time()-t0:.0f}s)")
    con.commit(); log.info(f"시세 완료: {tot:,}행 ({time.time()-t0:.0f}s)")

# ── (2) 투자자 ──────────────────────────────────────────────
def inv_one(code):
    """frgn 페이지를 TD 부근 페이지부터 훑어 FD까지 수집"""
    out = []
    try:
        r = requests.get(f"https://finance.naver.com/item/frgn.naver?code={code}&page=1",
                         headers=HDR, timeout=20); r.encoding = "euc-kr"
        t = [x for x in pd.read_html(io.StringIO(r.text)) if x.shape[1] >= 9 and x.shape[0] > 3]
        if not t: return out
        t0 = t[0].dropna(how="all"); t0.columns = range(t0.shape[1])
        ds = [str(x).replace(".", "") for x in t0[0] if str(x).replace(".", "").isdigit()]
        if not ds: return out
        latest = max(ds)
    except Exception:
        latest = None
    # TD까지 건너뛸 페이지 추정 (거래일 ≈ 246일/년, 20행/페이지) — 5페이지 여유
    page = 1
    if latest and latest > TD:
        yrs = (int(latest[:4]) * 12 + int(latest[4:6]) - int(TD[:4]) * 12 - int(TD[4:6])) / 12
        page = max(1, int(yrs * 246 / 20) - 5)
    miss = 0; prev_oldest = None
    while page <= 400:
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
                # 마지막 페이지를 넘기면 네이버가 같은 페이지를 반복 반환 → 진행 없으면 종료
                if oldest is not None and oldest == prev_oldest: break
                prev_oldest = oldest
            page += 1
        except Exception as e:
            log.warning(f"투자자 {code} p{page}: {str(e)[:40]}"); time.sleep(2); page += 1
    return out

if "--price-only" not in sys.argv:
    n = tot = 0; t0 = time.time()
    with ThreadPoolExecutor(4) as ex:
        for f in as_completed([ex.submit(inv_one, c) for c, _ in codes]):
            rows = f.result()
            if rows:
                con.executemany("UPDATE daily SET organ=?, frgn=?, "
                                "foreign_ratio=COALESCE(foreign_ratio,?) WHERE date=? AND ticker=?", rows)
                tot += len(rows)
            n += 1
            if n % 25 == 0:
                con.commit()
                el = time.time() - t0
                log.info(f"투자자 {n}/{len(codes)} ({tot:,}행, {el/60:.0f}분, 남은 예상 {(el/n*(len(codes)-n))/60:.0f}분)")
    con.commit(); log.info(f"투자자 완료: {tot:,}행 ({(time.time()-t0)/60:.0f}분)")

r = con.execute("SELECT count(*), min(date), max(date), sum(frgn IS NOT NULL) FROM daily "
                "WHERE date BETWEEN ? AND ?", (FD, TD)).fetchone()
print(f"[{FROM}~{TO}] {r[0]:,}행 · {r[1]}~{r[2]} · 외국인 {r[3]:,}행")
con.close()
