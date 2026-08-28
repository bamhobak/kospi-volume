"""액면분할/병합 기준 통일 (수정주가로 일원화)
문제: close(네이버 원본)와 open/high/low(FDR 수정주가)가 섞여 있고,
      과거 백필 시점에 따라 종목 내에서도 기준이 다름 → 거래량 비율 계산이 왜곡됨
해결: FDR 수정주가로 close/open/high/low/volume 을 통일하고,
      투자자 순매수(주 단위)도 같은 배율로 환산. 거래대금·시가총액은 분할과 무관하므로 유지.
사용: python fix_adjust.py [--dry]     (--dry 는 리포트만)
"""
import sqlite3, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd
import FinanceDataReader as fdr
import collect

DRY = "--dry" in sys.argv
log = collect.log
con = sqlite3.connect(collect.DB, timeout=300)
collect.init_db(con)
codes = [r[0] for r in con.execute("SELECT DISTINCT ticker FROM daily")]
log.info(f"기준 통일 대상 {len(codes)}종목 (dry={DRY})")

def one(code):
    try:
        d = fdr.DataReader(code, "2021-09-01")
        if d is None or len(d) == 0: return code, []
        d = d[(d["Close"] > 0) & (d["Volume"] >= 0)]
        return code, [(dt.strftime("%Y%m%d"), int(r["Open"]), int(r["High"]), int(r["Low"]),
                       int(r["Close"]), int(r["Volume"])) for dt, r in d.iterrows()]
    except Exception as e:
        log.warning(f"{code}: {str(e)[:50]}"); return code, []

fixed_rows = fixed_stocks = 0
report = []
n = 0
with ThreadPoolExecutor(8) as ex:
    for fut in as_completed([ex.submit(one, c) for c in codes]):
        code, rows = fut.result(); n += 1
        if not rows: continue
        cur = {r[0]: r for r in con.execute(
            "SELECT date, close, volume, indiv, organ, frgn FROM daily WHERE ticker=?", (code,))}
        upd, diff_dates = [], []
        for d_, o, h, l, c, v in rows:
            old = cur.get(d_)
            if old is None: continue
            oc, ov, oi, oo, of = old[1], old[2], old[3], old[4], old[5]
            factor = (oc / c) if (oc and c) else 1.0          # 원본기준 → 수정기준 환산 배율
            need = abs(factor - 1) > 0.02 or (ov and abs((v / ov) - 1) > 0.02 if ov else False)
            if not need: continue
            sc = lambda x: int(round(x * factor)) if x is not None else None
            upd.append((o, h, l, c, v, sc(oi), sc(oo), sc(of), d_, code))
            diff_dates.append(d_)
        if upd:
            fixed_stocks += 1; fixed_rows += len(upd)
            report.append((code, len(upd), min(diff_dates), max(diff_dates)))
            if not DRY:
                con.executemany("""UPDATE daily SET open=?, high=?, low=?, close=?, volume=?,
                                   indiv=?, organ=?, frgn=? WHERE date=? AND ticker=?""", upd)
        if n % 100 == 0:
            if not DRY: con.commit()
            log.info(f"진행 {n}/{len(codes)} · 보정 {fixed_stocks}종목 {fixed_rows}행")
if not DRY: con.commit()

report.sort(key=lambda x: -x[1])
print(f"\n기준 불일치 {fixed_stocks}종목 · {fixed_rows}행 {'(리포트만)' if DRY else '보정 완료'}\n")
print("| 종목 | 보정 행수 | 기간 |")
print("|---|---|---|")
names = {r[0]: r[1] for r in con.execute("SELECT ticker, name FROM daily GROUP BY ticker")}
for code, cnt, d0, d1 in report[:15]:
    print(f"| {names.get(code, code)}({code}) | {cnt} | {d0}~{d1} |")

if not DRY:
    q = """WITH x AS (SELECT ticker,name,date,close,LAG(close) OVER (PARTITION BY ticker ORDER BY date) pc
                      FROM daily WHERE date>='20230101')
           SELECT count(*) FROM x WHERE pc>0 AND (close*1.0/pc<0.6 OR close*1.0/pc>1.6)"""
    print(f"\n보정 후 남은 급변동(분할 의심) 행: {con.execute(q).fetchone()[0]}")
con.close()
