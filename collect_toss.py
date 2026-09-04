# -*- coding: utf-8 -*-
"""토스증권 Open API 수집 — 투자자별·프로그램매매·공매도·신용·대차.

왜 받나
  · 프로그램매매(차익·비차익)와 대차잔고는 우리가 갖지 못했던 재료다. 대차잔고는
    공매도의 앞단(빌린 주식이 늘면 곧 공매도가 나온다)이라 규칙 재료로 쓸 만하다.
  · 기관이 7 분할(금융투자·보험·투신·사모·은행·기타금융·연기금)로 나온다.
  · KRX 는 gap 2초로만 때릴 수 있는데 토스는 초당 10회다.
한계
  · 2019-04 부터만 준다. 그 이전은 KRX 백필로 받아야 한다(실측).

--days 를 주면 최근 N 거래일만 받는다(매일 갱신용). 없으면 2019-04 까지 거슬러 간다.
재개 가능: (종목, API) 단위로 done 에 기록하고 건너뛴다.
사용: python collect_toss.py [--days 10] [--workers 3] [--gap 0.3]
"""
import io, os, sys, time, json, sqlite3, logging, warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
import toss
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("toss")
arg = lambda k, d: sys.argv[sys.argv.index(k)+1] if k in sys.argv else d
DAYS = int(arg("--days", "0"))          # 0 = 전체 백필
W    = int(arg("--workers", "3"))
GAP  = float(arg("--gap", "0.3"))       # 워커 3 × 0.3초 ≈ 초당 10회 (한도)
SINCE = "2019-04-01"

DB = BASE/"data"/"toss.db"
SPEC = {   # API 경로 → (테이블, 레코드에서 뽑을 필드 맵)
 "investor-trading": ("investor", {
    "ind_buy":"individual.buyVolume","ind_sell":"individual.sellVolume","ind_net":"individual.netBuyVolume",
    "frg_buy":"foreigner.buyVolume","frg_sell":"foreigner.sellVolume","frg_net":"foreigner.netBuyVolume",
    "org_buy":"institution.buyVolume","org_sell":"institution.sellVolume","org_net":"institution.netBuyVolume",
    "fin_net":"institution.breakdown.financialInvestment.netBuyVolume",
    "ins_net":"institution.breakdown.insurance.netBuyVolume",
    "trust_net":"institution.breakdown.trust.netBuyVolume",
    "pef_net":"institution.breakdown.privateEquityFund.netBuyVolume",
    "bank_net":"institution.breakdown.bank.netBuyVolume",
    "othfin_net":"institution.breakdown.otherFinancialInstitution.netBuyVolume",
    "pension_net":"institution.breakdown.pensionFund.netBuyVolume",
    "corp_net":"otherCorporation.netBuyVolume",
    "frg_hold":"foreignerHolding.holdingQuantity","frg_rate":"foreignerHolding.holdingRate"}),
 "program-trades": ("program", {
    "arb_buy":"arbitrage.buyVolume","arb_sell":"arbitrage.sellVolume","arb_net":"arbitrage.netBuyVolume",
    "narb_buy":"nonArbitrage.buyVolume","narb_sell":"nonArbitrage.sellVolume","narb_net":"nonArbitrage.netBuyVolume"}),
 "short-selling": ("short", {
    "vol":"shortSellingVolume","amt":"shortSellingAmount",
    "vol_rate":"shortSellingVolumeRate","amt_rate":"shortSellingAmountRate"}),
 "credit-trades": ("credit", {
    "loan_new":"marginLoan.newQuantity","loan_ret":"marginLoan.returnQuantity",
    "loan_bal":"marginLoan.balanceQuantity","loan_bal_rate":"marginLoan.balanceRate",
    "loan_trd_rate":"marginLoan.tradingRate",
    "stk_new":"stockLoan.newQuantity","stk_ret":"stockLoan.returnQuantity",
    "stk_bal":"stockLoan.balanceQuantity"}),
 "securities-lending": ("lending", {
    "exec_qty":"executionQuantity","repay_qty":"repaymentQuantity",
    "bal_qty":"balanceQuantity","bal_amt":"balanceAmount"}),
}
def dig(d, path):
    for k in path.split("."):
        if not isinstance(d, dict): return None
        d = d.get(k)
    return d
con = sqlite3.connect(DB, timeout=600)
con.execute("PRAGMA journal_mode=WAL")
for p,(tb,cols) in SPEC.items():
    con.execute(f"CREATE TABLE IF NOT EXISTS {tb}(date TEXT, ticker TEXT, "
                + ",".join(f"{c} REAL" for c in cols) + ", PRIMARY KEY(date,ticker))")
con.execute("CREATE TABLE IF NOT EXISTS done(k TEXT PRIMARY KEY, n INTEGER, at TEXT)")
con.commit()

# 종목 목록 — 우리가 보고 있는 코스피·코스닥 전 종목
import collect as _c
kc = sqlite3.connect(f"file:{BASE}/data/kospi.db?mode=ro", uri=True)
TK = {r[0] for r in kc.execute("SELECT DISTINCT ticker FROM daily WHERE date>=?", ("20240101",))}
kc.close()
try:
    qc = sqlite3.connect(f"file:{BASE}/data/kosdaq.db?mode=ro", uri=True)
    TK |= {r[0] for r in qc.execute("SELECT DISTINCT ticker FROM daily WHERE date>=?", ("20240101",))}
    qc.close()
except Exception: pass
TK = sorted(TK)
tag = f"d{DAYS}" if DAYS else "full"
done = {r[0] for r in con.execute("SELECT k FROM done")}
todo = [(t,p) for t in TK for p in SPEC if f"{t}:{p}:{tag}" not in done]
log.info(f"토스 수집: 종목 {len(TK):,} × API {len(SPEC)} → 할 일 {len(todo):,} "
         f"({'최근 '+str(DAYS)+'일' if DAYS else SINCE+' 까지 전체'}) · 워커 {W} · gap {GAP}s")

def pull(tk, path):
    tb, cols = SPEC[path]
    rows, until, pages = [], None, 0
    while True:
        time.sleep(GAP)
        d = toss.get(f"/api/v1/stocks/{tk}/{path}", count=(min(DAYS,100) if DAYS else 100), until=until)
        if not isinstance(d, dict) or "_err" in d: break
        R = d.get("records") or []
        if not R: break
        for x in R:
            dt = (x.get("date") or "").replace("-","")
            if not dt or dt < SINCE.replace("-",""): continue
            rows.append((dt, tk) + tuple(dig(x, v) for v in cols.values()))
        pages += 1
        if DAYS or pages > 40: break                 # 매일 갱신은 1페이지면 충분
        until = d.get("nextUntil")
        if not until or min(x.get("date","9") for x in R) <= SINCE: break
    return tb, cols, rows

n = tot = 0; t0 = time.time()
CH = 25           # future 를 한꺼번에 13,835개 만들면 메모리가 터진다 — 청크로 나눠 제출한다
for s in range(0, len(todo), CH):
    chunk = todo[s:s+CH]
    with ThreadPoolExecutor(W) as ex:
        futs = {ex.submit(pull, t, p): (t, p) for t, p in chunk}
        for f in as_completed(futs):
            tk, path = futs[f]
            try: tb, cols, rows = f.result()
            except Exception as e:
                log.warning(f"  {tk} {path}: {str(e)[:60]}"); n += 1; continue
            if rows:
                ph = ",".join("?"*(2+len(cols)))
                con.executemany(f"INSERT OR REPLACE INTO {tb} VALUES({ph})", rows)
                tot += len(rows)
            con.execute("INSERT OR REPLACE INTO done VALUES(?,?,?)",
                        (f"{tk}:{path}:{tag}", len(rows), time.strftime("%Y-%m-%d %H:%M")))
            n += 1
    con.commit()
    el = time.time()-t0
    log.info(f"  {n:,}/{len(todo):,} · {tot:,}행 · {el/60:.0f}분 · 남은 {(el/max(n,1)*(len(todo)-n))/60:.0f}분")
log.info(f"완료: {tot:,}행")
for p,(tb,_) in SPEC.items():
    r = con.execute(f"SELECT min(date),max(date),count(*),count(DISTINCT ticker) FROM {tb}").fetchone()
    if r[0]: log.info(f"  {tb:<9} {r[0]}~{r[1]} · {r[2]:,}행 · {r[3]:,}종목")
con.close()
