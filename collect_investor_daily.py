# -*- coding: utf-8 -*-
"""투자자 11분할 — **날짜별** 수집(매일 갱신용).

기존 `collect_investor_detail.py` 는 종목별로 전체 이력을 받는다(3,091종목 × 몇 초 = 하루 이상).
그래서 매일 갱신에는 못 쓴다. 이 스크립트는 하루치를 **투자자 11종 × 시장 2개 = 22회 요청**으로 받는다.
같은 테이블(data/investor.db · flow11)에 넣으므로 두 방식이 섞여도 된다.

재개: done11d(date, market) 로 이미 받은 날은 건너뛴다.
사용: python collect_investor_daily.py [--days 10] [--gap 2.0]
⚠ KRX 는 과속하면 차단된다 — 기본 간격 2초, 순차 실행([[krx-rate-limit]]).
"""
import os, sqlite3, sys, time, logging, warnings
from pathlib import Path
import pandas as pd
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).parent
arg = lambda k, d: sys.argv[sys.argv.index(k)+1] if k in sys.argv else d
GAP = float(arg("--gap", "2.0")); DAYS = int(arg("--days", "10"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.FileHandler(BASE/"investor_daily.log", encoding="utf-8"),
                              logging.StreamHandler(sys.stdout)])
log = logging.getLogger()
for l in (BASE/".env").read_text(encoding="utf-8").splitlines():
    if "=" in l and not l.startswith("#"): k, v = l.split("=", 1); os.environ[k.strip()] = v.strip()
from pykrx import stock

COLS = [("fin","금융투자"),("ins","보험"),("tru","투신"),("pef","사모"),("bank","은행"),("ofin","기타금융"),
        ("pens","연기금"),("etc","기타법인"),("indiv","개인"),("frgn","외국인"),("ofrgn","기타외국인")]
DB = BASE/"data"/"investor.db"
con = sqlite3.connect(DB, timeout=900)
con.executescript(f"""
create table if not exists flow11(ticker text, date text, {', '.join(k+' real' for k,_ in COLS)});
create index if not exists ix_flow11 on flow11(ticker, date);
create table if not exists done11d(date text, market text, n integer, at text, primary key(date, market));
""")
con.commit()

# 대상 거래일 — 코스피 지수가 실제로 거래된 날
last = con.execute("select max(date) from flow11").fetchone()[0] or "20180102"
days = [d.strftime("%Y%m%d") for d in pd.bdate_range(
        pd.Timestamp.today() - pd.Timedelta(days=DAYS*2 + 5), pd.Timestamp.today())]
done = {(r[0], r[1]) for r in con.execute("select date,market from done11d")}
todo = [(d, m) for d in days for m in ("KOSPI", "KOSDAQ") if (d, m) not in done]
log.info(f"11분할 날짜별 수집 · 대상 {len(todo)}건 (최근 {DAYS}일 · flow11 최신 {last}) · 간격 {GAP}s")

def one(d, mk):
    """하루·한 시장의 11분할 순매수 거래대금을 종목별로 모은다."""
    out = {}
    for key, nm in COLS:
        time.sleep(GAP)
        try:
            df = stock.get_market_net_purchases_of_equities_by_ticker(d, d, mk, nm)
        except Exception as e:
            log.warning(f"  {d} {mk} {nm}: {str(e)[:60]}"); return None
        if df is None or df.empty: continue
        col = "순매수거래대금" if "순매수거래대금" in df.columns else df.columns[-1]
        for tk, v in df[col].items(): out.setdefault(tk, {})[key] = float(v)
    return out

n = tot = 0; t0 = time.time()
for d, mk in todo:
    res = one(d, mk)
    if res is None: continue
    if not res:                                   # 휴장일 — 표시만 남기고 넘어간다
        con.execute("insert or replace into done11d values(?,?,?,?)", (d, mk, 0, time.strftime("%H:%M")))
        con.commit(); n += 1; continue
    con.execute("delete from flow11 where date=? and ticker in (%s)" % ",".join("?"*len(res)),
                (d, *res.keys()))
    con.executemany(f"insert into flow11(ticker,date,{','.join(k for k,_ in COLS)}) "
                    f"values({','.join('?'*(2+len(COLS)))})",
                    [(tk, d, *[v.get(k) for k, _ in COLS]) for tk, v in res.items()])
    con.execute("insert or replace into done11d values(?,?,?,?)", (d, mk, len(res), time.strftime("%H:%M")))
    con.commit(); n += 1; tot += len(res)
    log.info(f"  [{n}/{len(todo)}] {d} {mk} {len(res)}종목 · 누적 {tot:,}행 · {(time.time()-t0)/60:.1f}분")
r = con.execute("select count(*),count(distinct ticker),min(date),max(date) from flow11").fetchone()
log.info(f"완료: flow11 {r[0]:,}행 · {r[1]}종목 · {r[2]}~{r[3]}")
con.close()
