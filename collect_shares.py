# -*- coding: utf-8 -*-
"""발행주식수 이력 수집 (DART stockTotqySttus) → data/dart/shares.db
   왜: 시가총액 이력이 없다(코스피 2023+ 뿐). 주식수가 있으면
       시총(규모) · 회전율(거래대금/시총) · PBR(시총/자본총계) 을 2018년부터 만들 수 있다.
   배치 불가(1개사/요청)라 오래 걸린다. 중단·재실행하면 이어받는다.
사용: python collect_shares.py [--workers 4] [--reprt 11011,11012,11013,11014]
"""
import io, os, sys, time, zipfile, sqlite3, requests, datetime as dt
import xml.etree.ElementTree as ET
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = Path(__file__).parent
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
W = int(arg("--workers", "4")); Y0 = int(arg("--from", "2018")); Y1 = dt.date.today().year
REPRT = tuple(arg("--reprt", "11011,11012,11013,11014").split(","))
KEY = os.environ.get("DART_API_KEY", "").strip() or [
    l.split("=", 1)[1].strip() for l in (BASE / ".env").read_text(encoding="utf-8").splitlines()
    if l.startswith("DART_API_KEY")][0]
DB = BASE / "data" / "dart" / "shares.db"; DB.parent.mkdir(parents=True, exist_ok=True)
con = sqlite3.connect(DB, timeout=900)
con.execute("""CREATE TABLE IF NOT EXISTS shares(
    stock_code TEXT, year INTEGER, reprt TEXT, se TEXT,
    issued REAL, treasury REAL, distb REAL, PRIMARY KEY(stock_code, year, reprt, se))""")
con.execute("CREATE TABLE IF NOT EXISTS done(k TEXT PRIMARY KEY, n INTEGER, at TEXT)")
con.commit()
with zipfile.ZipFile(BASE / "data" / "dart" / "corpcode.zip") as z: xml = z.read(z.namelist()[0])
MAP = {}
for e in ET.fromstring(xml).iter("list"):
    sc = (e.findtext("stock_code") or "").strip()
    if len(sc) == 6: MAP[e.findtext("corp_code")] = sc
have = set()
for db in ("kospi.db", "kosdaq.db", "delisted.db", "delisted_kd.db"):
    p = BASE / "data" / db
    if not p.exists(): continue
    try:
        c = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=300)
        have |= {r[0] for r in c.execute("SELECT DISTINCT ticker FROM daily")}; c.close()
    except Exception: pass
TARGET = [(cc, sc) for cc, sc in MAP.items() if sc in have]
# 중간에 멈춰도 쓸 수 있도록 사업보고서(연간)를 먼저 다 받고 분기로 넘어간다
PRI = {"11011": 0, "11012": 1, "11014": 2, "11013": 3}
JOBS = [(cc, sc, y, rp) for rp in sorted(REPRT, key=lambda x: PRI.get(x, 9))
        for y in range(Y0, Y1 + 1) for cc, sc in TARGET]
done = {r[0] for r in con.execute("SELECT k FROM done")}
JOBS = [j for j in JOBS if f"{j[1]}:{j[2]}:{j[3]}" not in done]
print(f"대상 {len(TARGET):,}종목 × {Y1-Y0+1}년 × 보고서 {len(REPRT)}종 = 총 {len(TARGET)*(Y1-Y0+1)*len(REPRT):,}건", flush=True)
print(f"남은 작업 **{len(JOBS):,}건** (완료 {len(done):,}) · 예상 {len(JOBS)*0.35/W/3600:.1f}시간", flush=True)
num = lambda v: float(str(v).replace(",", "")) if v and str(v).replace(",", "").replace("-", "").isdigit() else None
STOP = {"quota": False}
def one(job):
    cc, sc, y, rp = job
    if STOP["quota"]: return job, None
    for _ in range(3):
        try:
            r = requests.get("https://opendart.fss.or.kr/api/stockTotqySttus.json",
                             params=dict(crtfc_key=KEY, corp_code=cc, bsns_year=str(y), reprt_code=rp), timeout=40)
            j = r.json(); st = j.get("status")
            if st == "020": STOP["quota"] = True; return job, None
            if st != "000": return job, []          # 013 자료없음 등도 '처리됨'으로 기록
            out = []
            for x in (j.get("list") or []):
                se = (x.get("se") or "").strip()
                if "합계" in se or "보통주" in se or se == "":
                    out.append((sc, y, rp, se, num(x.get("istc_totqy")),
                                num(x.get("tesstk_co")), num(x.get("distb_stock_co"))))
            return job, out
        except Exception:
            time.sleep(1.0)
    return job, []
UPS = ("INSERT INTO shares VALUES (?,?,?,?,?,?,?) ON CONFLICT(stock_code,year,reprt,se) "
       "DO UPDATE SET issued=excluded.issued, treasury=excluded.treasury, distb=excluded.distb")
t0 = time.time(); n = tot = 0
with ThreadPoolExecutor(W) as ex:
    futs = [ex.submit(one, j) for j in JOBS]
    for f in as_completed(futs):
        job, rows = f.result()
        if rows is None: continue
        if rows: con.executemany(UPS, rows); tot += len(rows)
        con.execute("INSERT OR REPLACE INTO done VALUES (?,?,?)",
                    (f"{job[1]}:{job[2]}:{job[3]}", len(rows), dt.datetime.now().isoformat(timespec="seconds")))
        n += 1
        if n % 300 == 0:
            con.commit(); el = time.time() - t0
            print(f"진행 {n:,}/{len(JOBS):,} ({n/len(JOBS)*100:.1f}%) · {tot:,}행 · {el/60:.0f}분 경과 · 남은 {(len(JOBS)-n)*el/max(n,1)/3600:.1f}시간", flush=True)
con.commit()
if STOP["quota"]:
    print("⚠ DART 일일 한도 도달 — 내일 다시 실행하면 이어서 받습니다", flush=True)
r = con.execute("SELECT count(*), count(DISTINCT stock_code), min(year), max(year) FROM shares").fetchone()
print(f"완료: {r[0]:,}행 · {r[1]:,}종목 · {r[2]}~{r[3]} · {(time.time()-t0)/60:.0f}분", flush=True)
con.close()
