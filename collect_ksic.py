# -*- coding: utf-8 -*-
"""전 종목(상장+폐지) KSIC 업종코드 수집 → data/ksic.csv
   왜: industry.csv 는 '현재 상장' 종목만 담아 폐지 종목의 업종이 비어 있었다.
       업종 조건을 쓰는 규칙(P3·P4·D1·D2)이 폐지 종목을 평가조차 못 해 생존편향이 생겼다.
       KSIC(표준산업분류) 코드는 상장·폐지 구분 없이 DART 가 제공하므로 이걸로 통일한다.
   업종 그룹키 = KSIC 앞 3자리(중분류). 이름이 아니라 코드로 묶으므로 매핑 문제가 없다.
사용: python collect_ksic.py [--workers 4]   (한도 걸리면 다시 실행 = 이어받기)
"""
import io, os, sys, csv, time, sqlite3, zipfile, requests
import xml.etree.ElementTree as ET
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = Path(__file__).parent
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
W = int(arg("--workers", "4"))
KEY = os.environ.get("DART_API_KEY", "").strip() or [
    l.split("=", 1)[1].strip() for l in (BASE / ".env").read_text(encoding="utf-8").splitlines()
    if l.startswith("DART_API_KEY")][0]
OUT = BASE / "data" / "ksic.csv"
have = {}
if OUT.exists():
    for r in csv.DictReader(open(OUT, encoding="utf-8")): have[r["ticker"]] = r["ksic"]
need = set()
for db in ("kospi.db", "kosdaq.db", "delisted.db", "delisted_kd.db"):
    p = BASE / "data" / db
    if not p.exists(): continue
    try:
        c = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=300)
        need |= {r[0] for r in c.execute("SELECT DISTINCT ticker FROM daily")}; c.close()
    except Exception as e: print("건너뜀", db, str(e)[:50])
with zipfile.ZipFile(BASE / "data" / "dart" / "corpcode.zip") as z: xml = z.read(z.namelist()[0])
SC2CC = {}
for e in ET.fromstring(xml).iter("list"):
    sc = (e.findtext("stock_code") or "").strip()
    if len(sc) == 6: SC2CC[sc] = e.findtext("corp_code")
todo = [(t, SC2CC[t]) for t in sorted(need) if t in SC2CC and t not in have]
print(f"대상 {len(need):,}종목 · corp_code 확보 {len([t for t in need if t in SC2CC]):,} · "
      f"남은 작업 {len(todo):,} (완료 {len(have):,})", flush=True)
STOP = {"q": False}
def one(job):
    sc, cc = job
    if STOP["q"]: return sc, None
    for _ in range(3):
        try:
            j = requests.get("https://opendart.fss.or.kr/api/company.json",
                             params=dict(crtfc_key=KEY, corp_code=cc), timeout=30).json()
            st = j.get("status")
            if st == "020": STOP["q"] = True; return sc, None
            return sc, ((j.get("induty_code") or "").strip() if st == "000" else "")
        except Exception:
            time.sleep(1.0)
    return sc, ""
def save():
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write("ticker,ksic" + chr(10))
        for k, v in sorted(have.items()): fh.write(f"{k},{v}" + chr(10))
if todo:
    t0 = time.time(); n = 0
    with ThreadPoolExecutor(W) as ex:
        for f in as_completed([ex.submit(one, j) for j in todo]):
            sc, code = f.result()
            if code is None: continue
            have[sc] = code; n += 1
            if n % 200 == 0:
                save(); print(f"진행 {n:,}/{len(todo):,} · {time.time()-t0/1:.0f}초 경과", flush=True)
    save()
    if STOP["q"]: print("⚠ DART 일일 한도 도달 — 내일 다시 실행하면 이어받습니다", flush=True)
ok = {k: v for k, v in have.items() if v}
print(f"저장: {OUT.name} — {len(have):,}종목 중 KSIC 확보 {len(ok):,}", flush=True)
# 커버리지 점검
for db, nm in (("delisted.db", "코스피 폐지"), ("delisted_kd.db", "코스닥 폐지")):
    p = BASE / "data" / db
    if not p.exists(): continue
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=300)
    t = {r[0] for r in c.execute("SELECT DISTINCT ticker FROM daily")}; c.close()
    print(f"  {nm} {len(t)}종목 중 KSIC {len(t & set(ok)):,}개 ({len(t & set(ok))/max(len(t),1)*100:.0f}%)", flush=True)
