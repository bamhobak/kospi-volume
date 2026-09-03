# -*- coding: utf-8 -*-
"""업종 분류 이력 수집 — KRX 업종 지수의 구성 종목을 분기마다 받아 둔다.

지금은 업종 스냅샷이 2026-08-28 하나뿐이고 그걸 전 기간에 소급 적용한다.
그래서 그 사이 상장폐지된 종목은 업종을 모르고(2016년 종목의 98%), 업종을
조건으로 쓰는 5개 규칙이 과거 구간에서 거의 판정되지 않는다.

KRX 업종 지수(코스피 21 · 코스닥 20)는 구성 종목을 과거 날짜로 돌려준다.
그 시점의 실제 편입 종목이므로 현재 분류를 소급하는 것보다 정확하다.
업종은 자주 바뀌지 않으므로 분기 1회면 충분하다(기존 파이프라인도 분기 1회다).

data/kospi.db 의 sector 테이블에 kind='upjong' 으로 쌓는다. 재개 가능.
사용: python collect_sector_hist.py [--from 2016] [--gap 2.0]
"""
import io, sys, time, sqlite3, logging, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import pandas as pd
from pykrx import stock
import collect

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("sector")
arg = lambda k, d: sys.argv[sys.argv.index(k)+1] if k in sys.argv else d
Y0 = int(arg("--from", "2016")); GAP = float(arg("--gap", "2.0"))

# 업종 지수만 고른다 — 규모별(대형주)·전략지수(코스피200 …)는 업종이 아니다
KP_IDX = [str(x) for x in range(1005, 1028)]                      # 음식료·담배 ~ 제조
KQ_IDX = ["2012","2024","2026","2027","2029","2031","2037","2056","2058","2062",
          "2063","2065","2066","2067","2068","2070","2072","2074","2075","2077"]

con = sqlite3.connect(collect.DB, timeout=600)
con.execute("CREATE TABLE IF NOT EXISTS sector(snap TEXT, kind TEXT, gid TEXT, gname TEXT,"
            " ticker TEXT, PRIMARY KEY(snap,kind,gid,ticker))")
have = {(r[0], r[1]) for r in con.execute(
    "SELECT snap,gid FROM sector WHERE kind='upjong'")}

# 분기 스냅샷 날짜. 15일이 주말·휴장이면 KRX 가 빈 목록을 준다(2016-10-15 토요일에 실측).
# 평일로 당겨 두고, 그래도 비면 하루씩 앞으로 물러 재시도한다.
def _snapday(y, m):
    d = pd.Timestamp(year=y, month=m, day=15)
    while d.weekday() >= 5: d -= pd.Timedelta(days=1)
    return d.strftime("%Y%m%d")
snaps = [_snapday(y, m) for y in range(Y0, 2027) for m in (1, 4, 7, 10)]
snaps = [s for s in snaps if s <= pd.Timestamp.today().strftime("%Y%m%d")]
NAMES = {}
todo = [(s, i) for s in snaps for i in KP_IDX + KQ_IDX if (s, i) not in have]
log.info(f"업종 스냅샷 {len(snaps)}개 × 업종 {len(KP_IDX)+len(KQ_IDX)}개 → 받을 것 {len(todo)}건 "
         f"· 예상 {len(todo)*GAP/60:.0f}분")
n = rows = 0
for snap, idx in todo:
    try:
        time.sleep(GAP)
        if idx not in NAMES:
            try: NAMES[idx] = stock.get_index_ticker_name(idx)
            except Exception: NAMES[idx] = idx
        p = stock.get_index_portfolio_deposit_file(idx, snap)
        back = 0
        while not p and back < 5:            # 공휴일이면 직전 영업일로 물러선다
            back += 1
            d = (pd.Timestamp(snap) - pd.Timedelta(days=back)).strftime("%Y%m%d")
            time.sleep(GAP); p = stock.get_index_portfolio_deposit_file(idx, d)
        if p:
            con.executemany("INSERT OR REPLACE INTO sector VALUES(?,?,?,?,?)",
                            [(snap, "upjong", idx, NAMES[idx], t) for t in p])
            con.commit(); rows += len(p)
    except Exception as e:
        log.warning(f"  {snap} {idx} 실패: {str(e)[:60]}")
    n += 1
    if n % 100 == 0: log.info(f"  {n}/{len(todo)} · 누적 {rows:,}행")
log.info(f"완료: {rows:,}행")
for r in con.execute("SELECT snap,count(DISTINCT gid),count(DISTINCT ticker) FROM sector "
                     "WHERE kind='upjong' GROUP BY snap ORDER BY snap LIMIT 5"):
    log.info(f"  {r[0]}: 업종 {r[1]}개 · 종목 {r[2]}개")
con.close()
