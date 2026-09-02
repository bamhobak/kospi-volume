# -*- coding: utf-8 -*-
"""신용잔고 20일 증감률 수집 — [폭락반등] 규칙이 쓴다.

폭락 후 신용잔고가 크게 줄었다는 건 반대매매·손절이 이미 나와 매물이 소화됐다는 뜻이다.
안 줄었으면 빚내서 버티는 물량이 남아 추가 하락 압력이 있다. 실측에서 이 축 하나로
[폭락반등] 이 평균 +16.7%→+25.3%, 승률 78%→88% 로 갈렸다(신용 -20% 이하만 남길 때).

전 종목을 받으면 2,700콜이라 CI 시간 안에 못 끝낸다. 그런데 이 값이 필요한 곳은
[폭락반등] 후보뿐이고, 그 규칙은 '20일 -20% 폭락' 이 전제다. 그래서 20일 낙폭이
-15% 이하인 종목만 받는다(규칙 문턱 -20% 보다 넉넉히 잡아 경계값을 놓치지 않는다).
평상시 수십 종목, 폭락장에도 수백 종목이면 끝난다.

결과: data/credit_recent.csv (ticker, cr_chg20) — pipeline 이 table.json 으로 내보낸다.
사용: python collect_credit_recent.py [--max 600]
"""
import csv, os, sqlite3, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import collect, kis

BASE = Path(__file__).parent
OUT = BASE / "data" / "credit_recent.csv"
log = collect.log
arg = lambda k, d: sys.argv[sys.argv.index(k)+1] if k in sys.argv else d
MAXN = int(arg("--max", "800"))          # 폭락장 폭주 방지 상한(낙폭 큰 순)
DROP = float(arg("--drop", "-15"))       # 이 값 이하로 20일 하락한 종목만
WORKERS = int(arg("--workers", "4"))

def candidates():
    """20일 낙폭이 큰 종목 (코스피·코스닥). [폭락반등] 은 코스피지만 코스닥도 함께
       받아 두면 나중에 [낙폭과대] 에 같은 축을 얹을 때 쓸 수 있다."""
    out = {}
    for db in ("kospi.db", "kosdaq.db"):
        f = BASE / "data" / db
        if not f.exists(): continue
        con = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
        ds = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily ORDER BY date DESC LIMIT 21")]
        if len(ds) < 21: con.close(); continue
        last, prev = ds[0], ds[-1]
        rows = con.execute(
            "SELECT a.ticker, a.close, b.close FROM daily a JOIN daily b USING(ticker) "
            "WHERE a.date=? AND b.date=? AND a.close>0 AND b.close>0", (last, prev)).fetchall()
        con.close()
        for t, c1, c0 in rows:
            r = (c1/c0 - 1) * 100
            if r <= DROP: out[t] = r
    return [t for t, _ in sorted(out.items(), key=lambda x: x[1])][:MAXN]

def fetch(tk, token):
    """최근 30영업일 신용잔고 → 20일 증감률"""
    for attempt in range(4):
        try:
            st, d, _ = kis.call("/uapi/domestic-stock/v1/quotations/daily-credit-balance",
                                "FHPST04760000",
                                {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": tk,
                                 "FID_COND_SCR_DIV_CODE": "20476",
                                 "FID_INPUT_DATE_1": time.strftime("%Y%m%d")}, token=token)
        except Exception:
            time.sleep(0.5 + attempt); continue
        if d.get("rt_cd") != "0":
            time.sleep(0.5 + attempt); continue
        o = d.get("output") or d.get("output2") or []
        o = [x for x in (o if isinstance(o, list) else [o]) if x.get("deal_date")]
        o.sort(key=lambda x: x["deal_date"], reverse=True)      # 최신순
        if len(o) < 21: return None
        try:
            now = float(o[0]["whol_loan_rmnd_stcn"]); old = float(o[20]["whol_loan_rmnd_stcn"])
        except (TypeError, ValueError, KeyError):
            return None
        if not old: return None
        return round((now/old - 1) * 100, 2)
    return None

def main():
    cands = candidates()
    log.info(f"[신용잔고] 20일 낙폭 {DROP}% 이하 {len(cands)}종목 대상")
    if not cands:
        with open(OUT, "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerow(["ticker", "cr_chg20"])
        log.info("[신용잔고] 대상 없음 — 빈 파일만 남긴다"); return
    token = kis.get_token()
    res, t0 = {}, time.time()
    lock_gap = [0.0]
    def one(tk):
        w = 0.12 - (time.time() - lock_gap[0])
        if w > 0: time.sleep(w)
        lock_gap[0] = time.time()
        return tk, fetch(tk, token)
    with ThreadPoolExecutor(WORKERS) as ex:
        for f in as_completed([ex.submit(one, t) for t in cands]):
            tk, v = f.result()
            if v is not None: res[tk] = v
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh); w.writerow(["ticker", "cr_chg20"])
        w.writerows(sorted(res.items()))
    log.info(f"[신용잔고] {len(res)}/{len(cands)}종목 · {time.time()-t0:.0f}초 → {OUT.name}")

main()
