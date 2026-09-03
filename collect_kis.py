# -*- coding: utf-8 -*-
"""KIS Open API 수집 — 공매도 / 신용잔고 / 프로그램매매 (2018~현재)
   메인 DB를 건드리지 않고 data/kis/market.db 에 별도 저장. 재실행하면 이어서 수집.
사용: python collect_kis.py short|credit|program [--from 20180101] [--workers 4]
"""
import json, sqlite3, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import kis, collect

BASE = Path(__file__).parent
OUT = BASE / "data" / "kis"; OUT.mkdir(parents=True, exist_ok=True)
DB = OUT / "market.db"
log = collect.log
MODE = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "short"
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
FROM = arg("--from", "20180101")
W = int(arg("--workers", "4"))
num = lambda s: None if s in (None, "", "-") else (float(s) if "." in str(s) else int(float(s)))

SPEC = {
 "short": dict(path="/uapi/domestic-stock/v1/quotations/daily-short-sale", tr="FHPST04830000",
   table="short_sale", dkey="stck_bsop_date", per=100,
   cols=[("close","stck_clpr"),("volume","acml_vol"),("short_vol","ssts_cntg_qty"),
         ("short_ratio","ssts_vol_rlim"),("short_amt","ssts_tr_pbmn"),
         ("short_amt_ratio","ssts_tr_pbmn_rlim"),("short_cum","acml_ssts_cntg_qty"),
         ("avg_price","avrg_prc")],
   params=lambda d: {"FID_INPUT_DATE_1": FROM, "FID_INPUT_DATE_2": d}),
 "credit": dict(path="/uapi/domestic-stock/v1/quotations/daily-credit-balance", tr="FHPST04760000",
   table="credit", dkey="deal_date", per=30,
   cols=[("close","stck_prpr"),("volume","acml_vol"),("loan_new","whol_loan_new_stcn"),
         ("loan_rdmp","whol_loan_rdmp_stcn"),("loan_rmnd","whol_loan_rmnd_stcn"),
         ("loan_rmnd_amt","whol_loan_rmnd_amt"),("loan_rmnd_rate","whol_loan_rmnd_rate"),
         ("stln_new","whol_stln_new_stcn"),("stln_rmnd","whol_stln_rmnd_stcn")],
   params=lambda d: {"FID_COND_SCR_DIV_CODE": "20476", "FID_INPUT_DATE_1": d}),
 "program": dict(path="/uapi/domestic-stock/v1/quotations/comp-program-trade-daily", tr="FHPPG04650200",
   table="program", dkey="stck_bsop_date", per=30,
   cols=[("close","stck_clpr"),("volume","acml_vol"),("amount","acml_tr_pbmn"),
         ("prog_sell_vol","whol_smtn_seln_vol"),("prog_buy_vol","whol_smtn_shnu_vol"),
         ("prog_net_vol","whol_smtn_ntby_qty"),("prog_sell_amt","whol_smtn_seln_tr_pbmn"),
         ("prog_buy_amt","whol_smtn_shnu_tr_pbmn"),("prog_net_amt","whol_smtn_ntby_tr_pbmn")],
   params=lambda d: {"FID_INPUT_DATE_1": d, "FID_INPUT_DATE_2": d}),
}
S = SPEC[MODE]
CN = [c for c, _ in S["cols"]]

con = sqlite3.connect(DB, timeout=900)
con.execute(f"""CREATE TABLE IF NOT EXISTS {S['table']}(
    date TEXT, ticker TEXT, {', '.join(c+' REAL' for c in CN)}, PRIMARY KEY(date,ticker))""")
con.execute(f"CREATE INDEX IF NOT EXISTS ix_{S['table']}_t ON {S['table']}(ticker,date)")
con.execute("CREATE TABLE IF NOT EXISTS done(mode TEXT, ticker TEXT, n INTEGER, at TEXT, PRIMARY KEY(mode,ticker))")
con.commit()
done = {r[0] for r in con.execute("SELECT ticker FROM done WHERE mode=?", (MODE,))}

MKT = arg("--market", "KOSPI")               # KOSPI | KOSDAQ | DELISTED
SRC = BASE / "data" / {"KOSPI": "kospi.db", "KOSDAQ": "kosdaq.db",
                       "DELISTED_KD": "delisted_kd.db"}.get(MKT, "delisted.db")
c2 = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True)
if MKT == "DELISTED_KD":                      # 폐지 코스닥: 목록 CSV 로 한정
    import csv as _csv
    codes = [r["Symbol"] for r in _csv.DictReader(open(BASE / "data" / "kosdaq_delisted.csv", encoding="utf-8"))]
elif MKT == "DELISTED":                       # 상장폐지 종목 DB엔 market 컬럼이 없음
    codes = [r[0] for r in c2.execute("SELECT DISTINCT ticker FROM daily")]
elif MKT == "KOSPI":
    codes = [r[0] for r in c2.execute("SELECT DISTINCT ticker FROM daily WHERE market=?", (MKT,))]
else:                                         # 거래 불가 종목까지 긁을 필요 없음
    codes = [r[0] for r in c2.execute(
        "SELECT ticker FROM daily WHERE market=? AND volume>0 AND close>0 "
        f"GROUP BY ticker HAVING avg(volume*close)/1e8 >= {float(arg('--min-amt','1'))}", (MKT,))]
c2.close()
todo = [t for t in sorted(codes) if t not in done]
log.info(f"[{MODE}/{MKT}] 대상 {len(todo)}종목 (완료 {len(done)}) · {FROM}~ · 워커 {W}")

TOKEN = kis.get_token()
lock = threading.Lock(); last = [0.0]
GAP = float(arg("--gap", "0.15"))
def throttle(gap=GAP):
    with lock:
        w = gap - (time.time() - last[0])
        if w > 0: time.sleep(w)
        last[0] = time.time()

import datetime as _dt
def fetch(tk):
    """오류 시 재시도. 끝까지 못 받으면 done=False 로 반환해 다음 실행에서 재개."""
    rows, anchor, seen = [], time.strftime("%Y%m%d"), set()
    complete = False
    for _ in range(200):
        p = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": tk}
        p.update(S["params"](anchor))
        ok = False
        for attempt in range(5):                      # 레이트리밋/일시오류 재시도
            throttle()
            try:
                st, d, _ = kis.call(S["path"], S["tr"], p, token=TOKEN)
            except Exception:
                time.sleep(1 + attempt); continue
            rt = d.get("rt_cd")
            if rt == "0": ok = True; break
            msg = (d.get("msg1") or "")[:40]
            if "조회할 자료가 없습니다" in msg or d.get("msg_cd") in ("MCA00000",):
                complete = True; break
            time.sleep(1 + attempt * 2)
        if complete: break
        if not ok:
            log.warning(f"[{MODE}] {tk} 재시도 초과 (anchor={anchor}) — 미완료로 남김")
            break
        o = d.get("output2") or d.get("output") or []
        o = o if isinstance(o, list) else [o]
        got = []
        for x in o:
            dt_ = x.get(S["dkey"])
            if not dt_ or len(dt_) != 8 or dt_ in seen: continue
            seen.add(dt_); got.append(dt_)
            rows.append((dt_, tk, *[num(x.get(src)) for _, src in S["cols"]]))
        if not got: complete = True; break          # 더 이상 과거 데이터 없음
        oldest = min(got)
        if oldest <= FROM: complete = True; break
        anchor = (_dt.date(int(oldest[:4]), int(oldest[4:6]), int(oldest[6:])) - _dt.timedelta(days=1)).strftime("%Y%m%d")
    return tk, [r for r in rows if r[0] >= FROM], complete

n = tot = 0; t0 = time.time()
ph = ",".join("?" * (2 + len(CN)))
with ThreadPoolExecutor(W) as ex:
    for f in as_completed([ex.submit(fetch, t) for t in todo]):
        tk, rows, complete = f.result()
        if rows:
            con.executemany(f"INSERT OR IGNORE INTO {S['table']} (date,ticker,{','.join(CN)}) VALUES ({ph})", rows)
            tot += len(rows)
        if complete:
            con.execute("INSERT OR REPLACE INTO done VALUES (?,?,?,?)", (MODE, tk, len(rows), time.strftime("%H:%M")))
        n += 1
        if n % 25 == 0:
            con.commit(); el = time.time() - t0
            log.info(f"[{MODE}] {n}/{len(todo)} ({tot:,}행, {el/60:.1f}분, 남은 {(el/n*(len(todo)-n))/60:.0f}분)")
con.commit()
r = con.execute(f"SELECT count(*),count(DISTINCT ticker),min(date),max(date) FROM {S['table']}").fetchone()
print(f"[{MODE}] {r[0]:,}행 · {r[1]}종목 · {r[2]}~{r[3]}")
con.close()
