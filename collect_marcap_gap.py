# -*- coding: utf-8 -*-
"""시가총액·상장주식수 구멍 메우기 — 2018~2022 만 아무도 안 받았다.

배경(2026-09-06 발견): kospi.db 의 marcap 유효율이 2005~2017 100% · **2018~2022 0%** · 2023~ 100% 다.
네이버 기반 일일 수집은 시총을 저장하지 않았고, KRX 백필은 2005~2017 만 했기 때문이다.
그 탓에 시총 조건을 쓰는 **[외인 매집] 이 2018~2022 구간 신호 0건**이 됐다(과거 검증에서 드러남).

전종목 OHLCV 를 다시 받을 필요는 없다. `get_market_cap_by_ticker` 는 날짜당 1콜로
종가·시가총액·거래량·거래대금·상장주식수를 준다. 코스피/코스닥 각각 받아 daily 를 UPDATE 한다.
⚠ KRX 는 과속하면 차단된다 — 콜 간격 기본 1.6초, 순차.
사용: python collect_marcap_gap.py [--from 20180101] [--to 20221231] [--gap 1.6]
"""
import os, sqlite3, sys, time, logging, warnings
from pathlib import Path
import pandas as pd
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).parent
arg = lambda k, d: sys.argv[sys.argv.index(k)+1] if k in sys.argv else d
FROM, TO, GAP = arg("--from", "20180101"), arg("--to", "20221231"), float(arg("--gap", "1.6"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S",
                    handlers=[logging.FileHandler(BASE/"marcap_gap.log", encoding="utf-8"),
                              logging.StreamHandler(sys.stdout)])
log = logging.getLogger()
for l in (BASE/".env").read_text(encoding="utf-8").splitlines():
    if "=" in l and not l.startswith("#"): k, v = l.split("=", 1); os.environ[k.strip()] = v.strip()
from pykrx import stock

DB = {"KOSPI": BASE/"data"/"kospi.db", "KOSDAQ": BASE/"data"/"kosdaq.db"}
con = {m: sqlite3.connect(p, timeout=900) for m, p in DB.items()}
for c in con.values():
    c.execute("CREATE TABLE IF NOT EXISTS done_marcap(date TEXT, mk TEXT, n INTEGER, at TEXT, "
              "PRIMARY KEY(date, mk))")
    c.commit()

# 채울 날짜 = 그 시장 DB 에 있는 거래일 중 marcap 이 비어 있고 아직 안 받은 날
todo = []
for m, c in con.items():
    have = {r[0] for r in c.execute("SELECT date FROM done_marcap WHERE mk=?", (m,))}
    q = ("SELECT date, sum(marcap IS NOT NULL AND marcap>0), count(*) FROM daily "
         "WHERE date>=? AND date<=? GROUP BY date ORDER BY date")
    for d, ok, n in c.execute(q, (FROM, TO)):
        if d in have or (ok or 0) >= n*0.5: continue
        todo.append((d, m))
todo.sort()
log.info(f"시총 구멍 메우기: {len(todo)}건 ({FROM}~{TO}) · 콜간격 {GAP}s · 예상 {len(todo)*GAP/3600:.1f}시간")

n = upd = 0; t0 = time.time()
for d, m in todo:
    time.sleep(GAP)
    try:
        df = stock.get_market_cap_by_ticker(d, market=m)
    except Exception as e:
        log.warning(f"  {d} {m}: {str(e)[:60]}"); continue
    n += 1
    if df is None or df.empty:                      # 휴장일 — 표시만 남긴다
        con[m].execute("INSERT OR REPLACE INTO done_marcap VALUES(?,?,?,?)", (d, m, 0, time.strftime("%H:%M")))
        con[m].commit(); continue
    rows = [(int(r["시가총액"]), int(r["상장주식수"]), d, t) for t, r in df.iterrows()
            if r.get("시가총액") and r.get("상장주식수")]
    con[m].executemany("UPDATE daily SET marcap=?, shares=? WHERE date=? AND ticker=?", rows)
    con[m].execute("INSERT OR REPLACE INTO done_marcap VALUES(?,?,?,?)", (d, m, len(rows), time.strftime("%H:%M")))
    con[m].commit(); upd += len(rows)
    if n % 50 == 0:
        el = time.time()-t0
        log.info(f"  {n}/{len(todo)} · {upd:,}행 갱신 · {el/60:.0f}분 · 남은 {(el/n*(len(todo)-n))/60:.0f}분")
for m, c in con.items():
    r = c.execute("SELECT sum(marcap IS NOT NULL AND marcap>0)*100/count(*) FROM daily WHERE date>=? AND date<=?",
                  (FROM, TO)).fetchone()[0]
    log.info(f"완료 {m}: {FROM}~{TO} marcap 유효율 {r or 0:.0f}%")
    c.close()
log.info(f"총 {upd:,}행 갱신 · {(time.time()-t0)/60:.0f}분")
