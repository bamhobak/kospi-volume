# -*- coding: utf-8 -*-
"""DART 공시 수집 (OpenDART list.json) — 2018-01-01 ~ 현재
   메인 DB를 건드리지 않고 data/dart/disclosures.db 에 별도 저장.
   공시는 접수일자(rcept_dt)가 명확해 과거 백테스트에 미래참조 없이 쓸 수 있음.
사용: python collect_dart.py [--from 20180101] [--to 20260828] [--workers 4]
"""
import json, sqlite3, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests
import collect

BASE = Path(__file__).parent
OUT = BASE / "data" / "dart"; OUT.mkdir(parents=True, exist_ok=True)
DB = OUT / "disclosures.db"
log = collect.log
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
FROM, TO = arg("--from", "20180101"), arg("--to", time.strftime("%Y%m%d"))
W = int(arg("--workers", "4"))
KEY = None
for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("DART_API_KEY="): KEY = line.split("=", 1)[1].strip()
assert KEY, ".env 에 DART_API_KEY 없음"

CORP = json.load(open(OUT / "corp_code.json", encoding="utf-8"))
con = sqlite3.connect(DB, timeout=600)
con.execute("""CREATE TABLE IF NOT EXISTS disclosure(
    rcept_no TEXT PRIMARY KEY, corp_code TEXT, stock_code TEXT, corp_name TEXT,
    rcept_dt TEXT, report_nm TEXT, flr_nm TEXT, rm TEXT)""")
con.execute("CREATE INDEX IF NOT EXISTS ix_disc_stock ON disclosure(stock_code, rcept_dt)")
con.execute("CREATE INDEX IF NOT EXISTS ix_disc_dt ON disclosure(rcept_dt)")
con.execute("CREATE TABLE IF NOT EXISTS done(corp_code TEXT PRIMARY KEY, n INTEGER, at TEXT)")
con.commit()
# done 은 종목 단위라 기간을 바꿔도 이미 받은 종목을 건너뛴다. 과거 구간을 따로
# 받으려면 키를 갈라야 한다 — 2018 이전 요청이면 연도 태그를 붙인다(2026-09-03).
TAG = "" if FROM >= "20180101" else ":" + FROM[:4]
done = {r[0] for r in con.execute("SELECT corp_code FROM done")}
todo = [(sc, v["corp_code"], v["corp_name"]) for sc, v in CORP.items()
        if v["corp_code"] + TAG not in done]
log.info(f"DART 공시 수집: 대상 {len(todo)}종목 (완료 {len(done)}) · {FROM}~{TO}")

URL = "https://opendart.fss.or.kr/api/list.json"
def fetch(stock, cc, nm):
    rows, page = [], 1
    while page <= 200:
        p = {"crtfc_key": KEY, "corp_code": cc, "bgn_de": FROM, "end_de": TO,
             "page_no": page, "page_count": 100}
        try:
            d = requests.get(URL, params=p, timeout=30).json()
        except Exception as e:
            time.sleep(2); 
            try: d = requests.get(URL, params=p, timeout=30).json()
            except Exception: log.warning(f"{nm} p{page}: {str(e)[:40]}"); break
        st = d.get("status")
        if st == "013": break                      # 조회 데이터 없음
        if st == "020":                            # 사용한도 초과
            log.error("DART 일일 사용한도 초과 — 중단"); raise SystemExit(2)
        if st != "000":
            log.warning(f"{nm}: status={st} {d.get('message')}"); break
        for x in d.get("list") or []:
            rows.append((x.get("rcept_no"), cc, stock, x.get("corp_name"),
                         x.get("rcept_dt"), x.get("report_nm"), x.get("flr_nm"), x.get("rm")))
        if page >= int(d.get("total_page") or 1): break
        page += 1
    return cc, rows

n = tot = 0; t0 = time.time()
with ThreadPoolExecutor(W) as ex:
    futs = [ex.submit(fetch, s, c, nm) for s, c, nm in todo]
    for f in as_completed(futs):
        cc, rows = f.result()
        if rows:
            con.executemany("INSERT OR IGNORE INTO disclosure VALUES (?,?,?,?,?,?,?,?)", rows)
            tot += len(rows)
        con.execute("INSERT OR REPLACE INTO done VALUES (?,?,?)",
                    (cc + TAG, len(rows), time.strftime("%Y-%m-%d %H:%M")))
        n += 1
        if n % 50 == 0:
            con.commit(); el = time.time() - t0
            log.info(f"{n}/{len(todo)} ({tot:,}건, {el/60:.1f}분, 남은 예상 {(el/n*(len(todo)-n))/60:.0f}분)")
con.commit()
r = con.execute("SELECT count(*), count(DISTINCT stock_code), min(rcept_dt), max(rcept_dt) FROM disclosure").fetchone()
print(f"공시 {r[0]:,}건 · {r[1]}종목 · {r[2]}~{r[3]}")
print("상위 공시 유형:")
for nm_, c in con.execute("""SELECT report_nm, count(*) c FROM disclosure GROUP BY report_nm
                             ORDER BY c DESC LIMIT 12"""):
    print(f"   {c:>7,}  {nm_[:50]}")
con.close()
