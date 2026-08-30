# -*- coding: utf-8 -*-
"""DART 재무 이력 수집 — fnlttMultiAcnt (100개사 배치) → data/dart/financials.db
   대상: corpCode.xml 로 매핑되는 상장 이력 전 종목(폐지 포함, 생존편향 제거)
   기간: 2018~현재 × 분기 4개 보고서
   재실행하면 이미 받은 (연도,보고서,배치)는 건너뛴다.
사용: python collect_dart_fin.py [--from 2018] [--workers 4]
"""
import io, os, sys, time, zipfile, sqlite3, requests, datetime as dt
import xml.etree.ElementTree as ET
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = Path(__file__).parent
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
Y0 = int(arg("--from", "2018")); W = int(arg("--workers", "4"))
Y1 = dt.date.today().year
KEY = os.environ.get("DART_API_KEY", "").strip()
if not KEY:
    KEY = [l.split("=", 1)[1].strip() for l in (BASE / ".env").read_text(encoding="utf-8").splitlines()
           if l.startswith("DART_API_KEY")][0]
DB = BASE / "data" / "dart" / "financials.db"
DB.parent.mkdir(parents=True, exist_ok=True)
con = sqlite3.connect(DB, timeout=900)
con.execute("""CREATE TABLE IF NOT EXISTS fin(
    corp_code TEXT, stock_code TEXT, year INTEGER, reprt TEXT, fs_div TEXT,
    account TEXT, amount REAL, PRIMARY KEY(corp_code, year, reprt, fs_div, account))""")
con.execute("CREATE INDEX IF NOT EXISTS ix_fin ON fin(stock_code, year, reprt)")
con.execute("CREATE TABLE IF NOT EXISTS done(k TEXT PRIMARY KEY, n INTEGER, at TEXT)")
con.commit()

# ── corp_code ↔ stock_code ──────────────────────────────────
zp = BASE / "data" / "dart" / "corpcode.zip"
if not zp.exists() or zp.stat().st_size < 1000:
    r = requests.get("https://opendart.fss.or.kr/api/corpCode.xml", params=dict(crtfc_key=KEY), timeout=180)
    zp.write_bytes(r.content)
with zipfile.ZipFile(zp) as z: xml = z.read(z.namelist()[0])
MAP = {}
for e in ET.fromstring(xml).iter("list"):
    sc = (e.findtext("stock_code") or "").strip()
    if len(sc) == 6: MAP[e.findtext("corp_code")] = sc
# 우리가 가진 종목만
have = set()
for db in ("kospi.db", "kosdaq.db", "delisted.db", "delisted_kd.db"):
    p = BASE / "data" / db
    if not p.exists(): continue
    try:
        c = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=300)
        have |= {r[0] for r in c.execute("SELECT DISTINCT ticker FROM daily")}; c.close()
    except Exception as e: print("건너뜀", db, str(e)[:40])
TARGET = [(cc, sc) for cc, sc in MAP.items() if sc in have]
print(f"대상 {len(TARGET):,}종목 (보유 {len(have):,}개 중) · {Y0}~{Y1} × 보고서 4종", flush=True)
BATCH = [TARGET[i:i + 100] for i in range(0, len(TARGET), 100)]
REPRT = ("11011", "11012", "11013", "11014")   # 사업/반기/1분기/3분기
JOBS = [(y, rp, bi) for y in range(Y0, Y1 + 1) for rp in REPRT for bi in range(len(BATCH))]
if "--refresh" in sys.argv:      # 최근 연도는 새 분기 보고서가 계속 나오므로 다시 받는다
    ry = int(arg("--refresh-years", "2"))
    con.execute("DELETE FROM done WHERE CAST(substr(k,1,4) AS INTEGER) >= ?", (Y1 - ry + 1,)); con.commit()
done = {r[0] for r in con.execute("SELECT k FROM done")}
JOBS = [j for j in JOBS if f"{j[0]}:{j[1]}:{j[2]}" not in done]
print(f"남은 작업 {len(JOBS):,}건 (완료 {len(done):,})", flush=True)

def fetch(job):
    y, rp, bi = job
    batch = BATCH[bi]; codes = ",".join(c for c, _ in batch)
    sc_of = dict(batch)
    for attempt in range(3):
        try:
            r = requests.get("https://opendart.fss.or.kr/api/fnlttMultiAcnt.json",
                             params=dict(crtfc_key=KEY, corp_code=codes, bsns_year=str(y), reprt_code=rp),
                             timeout=90)
            j = r.json()
            if j.get("status") == "020":      # 일일 한도 초과
                return job, None, "quota"
            rows = []
            for x in (j.get("list") or []):
                a = (x.get("thstrm_amount") or "").replace(",", "").strip()
                if not a or a in ("-", "─"): continue
                try: v = float(a)
                except ValueError: continue
                rows.append((x["corp_code"], sc_of.get(x["corp_code"]), y, rp,
                             x.get("fs_div") or "", x.get("account_nm") or "", v))
            return job, rows, j.get("status")
        except Exception:
            time.sleep(1.5)
    return job, [], "err"

UPS = ("INSERT INTO fin(corp_code,stock_code,year,reprt,fs_div,account,amount) VALUES (?,?,?,?,?,?,?) "
       "ON CONFLICT(corp_code,year,reprt,fs_div,account) DO UPDATE SET amount=excluded.amount")
t0 = time.time(); n = tot = 0; quota = False
with ThreadPoolExecutor(W) as ex:
    futs = [ex.submit(fetch, j) for j in JOBS]
    for f in as_completed(futs):
        job, rows, st = f.result()
        if st == "quota":
            quota = True; continue
        if rows is None: continue
        if rows: con.executemany(UPS, rows); tot += len(rows)
        con.execute("INSERT OR REPLACE INTO done VALUES (?,?,?)",
                    (f"{job[0]}:{job[1]}:{job[2]}", len(rows), dt.datetime.now().isoformat(timespec="seconds")))
        n += 1
        if n % 100 == 0:
            con.commit()
            el = time.time() - t0
            print(f"진행 {n:,}/{len(JOBS):,} · {tot:,}행 · {el/60:.1f}분 경과 · 남은 예상 {(len(JOBS)-n)*el/max(n,1)/60:.1f}분", flush=True)
con.commit()
if quota: print("⚠ DART 일일 한도(020) 도달 — 내일 다시 실행하면 이어서 받습니다", flush=True)
r = con.execute("SELECT count(*), count(DISTINCT stock_code), min(year), max(year) FROM fin").fetchone()
print(f"완료: {r[0]:,}행 · {r[1]:,}종목 · {r[2]}~{r[3]} · {(time.time()-t0)/60:.1f}분", flush=True)
print("계정 종류:", [x[0] for x in con.execute("SELECT account, count(*) c FROM fin GROUP BY 1 ORDER BY c DESC LIMIT 20")], flush=True)
con.close()
